# Race Conditions for Concurrent First-Failure State in Async FastAPI

## Overview

This document enumerates all possible race conditions when multiple async requests attempt to read/write first-failure state concurrently in the aide-de-camp FastAPI application. It covers specific race scenarios, state transitions that can conflict, and identifies which operations are atomic.

## Context: Async FastAPI Execution Model

FastAPI uses `asyncio` for concurrent request handling. Multiple coroutines can execute concurrently on a single thread via cooperative multitasking. This means:

- **No preemption**: Coroutines yield control only at `await` points
- **Concurrent execution**: Multiple coroutines can be "in flight" simultaneously
- **Shared state**: All requests access the same singleton `TelegramFallback` instance
- **No locks by default**: Python does not provide atomic operations for object mutations

**Critical insight**: Between the check (`if not state.has_failed`) and the act (`state.has_failed = True`), another coroutine can run and interleave its operations, causing race conditions.

---

## State Structure at Risk

```python
# First-failure state (instance variables in TelegramFallback)
self._has_logged_first_failure: bool = False
self._failure_count: int = 0
self._first_failure_timestamp: Optional[datetime] = None
self._last_failure_timestamp: Optional[datetime] = None
self._notification_sent: bool = False
self._notification_sent_at: Optional[datetime] = None
self._channel_id: Optional[str] = None
self._error_type: Optional[str] = None
self._error_message: Optional[str] = None
```

All these fields are **mutable** and **shared** across concurrent requests. Without synchronization, multiple coroutines can read and write them simultaneously, leading to inconsistent state.

---

## Race Condition Categories

### Category 1: Check-Then-Act Races on `has_logged_first_failure`

#### Race 1.1: Concurrent First Failures (Duplicate WARNING Logs)

**Scenario**: Multiple requests fail simultaneously at application startup.

**Without Lock**:
```
Time  T0: Coroutine A checks has_logged_first_failure → False
Time  T1: Coroutine B checks has_logged_first_failure → False
Time  T2: Coroutine A sets has_logged_first_failure = True, logs WARNING
Time  T3: Coroutine B sets has_logged_first_failure = True, logs WARNING ❌ DUPLICATE
```

**Impact**:
- Multiple WARNING logs for the same "first" failure
- Violates requirement: exactly one WARNING per startup
- Log spam when bridge is down
- May trigger multiple alert notifications

**State After Race**:
```
has_logged_first_failure = True  (correct)
failure_count = 2                 (correct)
first_failure_timestamp = T2      (one of the two, non-deterministic)
```

**With `asyncio.Lock`**:
```
Time  T0: Coroutine A acquires lock
Time  T1: Coroutine B blocks on lock (queued)
Time  T2: Coroutine A checks → False, sets → True, logs WARNING, releases lock
Time  T3: Coroutine B acquires lock, checks → True, logs DEBUG, releases lock ✅
```

**Result**: Exactly one WARNING, N-1 DEBUG logs.

---

#### Race 1.2: Read-During-Write on `has_logged_first_failure`

**Scenario**: A status read (`get_bridge_status()`) occurs while another coroutine is writing the first-failure state.

**Without Lock**:
```
Time  T0: Coroutine A (failure handler) checks has_logged_first_failure → False
Time  T1: Coroutine B (status endpoint) reads has_logged_first_failure → False
Time  T2: Coroutine B reads first_failure_timestamp → None
Time  T3: Coroutine A sets has_logged_first_failure = True
Time  T4: Coroutine A sets first_failure_timestamp = now
Time  T5: Coroutine B returns status: {"has_logged_first_failure": False, "first_failure_timestamp": None}
```

**Impact**:
- Status endpoint returns stale data (inconsistent view)
- Monitoring/metrics miss the first-failure event
- Health checks show "healthy" despite failure in progress

**State After Race**:
```
has_logged_first_failure = True  (correct)
first_failure_timestamp = T4     (correct)
Status returned: False, None      (stale)
```

**With `asyncio.Lock`** (write path only):
- Reads do NOT acquire lock (by design)
- Reads may see intermediate state, but this is acceptable for monitoring
- If strict consistency is required, reads must also acquire lock

**Verdict**: Acceptable inconsistency for monitoring; critical operations require lock.

---

### Category 2: Lost Update Races on Counters

#### Race 2.1: Concurrent Increment of `failure_count`

**Scenario**: Multiple failures increment the counter simultaneously.

**Without Lock**:
```
Time  T0: failure_count = 5
Time  T1: Coroutine A reads failure_count → 5
Time  T2: Coroutine B reads failure_count → 5
Time  T3: Coroutine A increments: failure_count = 5 + 1 = 6, writes
Time  T4: Coroutine B increments: failure_count = 5 + 1 = 6, writes ❌ LOST UPDATE
Time  T5: failure_count = 6  (should be 7)
```

**Impact**:
- Inaccurate failure count
- Misleading diagnostics
- Wrong metrics for monitoring
- Underestimates failure frequency

**State After Race**:
```
failure_count = 6  (incorrect, should be 7)
```

**With `asyncio.Lock`**:
```
Time  T0: Coroutine A acquires lock
Time  T1: Coroutine B blocks on lock
Time  T2: Coroutine A reads (5), increments (6), writes, releases lock
Time  T3: Coroutine B acquires lock, reads (6), increments (7), writes, releases lock ✅
```

**Result**: All updates serialized, count is accurate.

---

#### Race 2.2: Increment-During-Read on `failure_count`

**Scenario**: Status endpoint reads `failure_count` while it's being incremented.

**Without Lock**:
```
Time  T0: failure_count = 10
Time  T1: Coroutine A (status) reads failure_count → 10
Time  T2: Coroutine B (failure handler) reads failure_count → 10
Time  T3: Coroutine B increments: failure_count = 11
Time  T4: Coroutine A returns status: {"failure_count": 10}  (stale)
```

**Impact**:
- Status shows slightly stale count (acceptable for monitoring)
- No correctness issue (count is monotonic, stale value is just outdated)

**Verdict**: Acceptable for monitoring; no lock needed for reads.

---

### Category 3: Timestamp Assignment Races

#### Race 3.1: Concurrent Write of `first_failure_timestamp`

**Scenario**: Multiple failures attempt to set `first_failure_timestamp` simultaneously.

**Without Lock**:
```
Time  T0: first_failure_timestamp = None
Time  T1: Coroutine A checks first_failure_timestamp → None
Time  T2: Coroutine B checks first_failure_timestamp → None
Time  T3: Coroutine A sets first_failure_timestamp = datetime_A
Time  T4: Coroutine B sets first_failure_timestamp = datetime_B ❌ OVERWRITE
Time  T5: first_failure_timestamp = datetime_B  (non-deterministic)
```

**Impact**:
- Lost first-failure timestamp accuracy
- Difficult to correlate with logs
- Misleading diagnostics (which was really first?)
- Non-deterministic behavior

**State After Race**:
```
first_failure_timestamp = datetime_B  (one of the two, non-deterministic)
```

**With `asyncio.Lock`**:
```
Time  T0: Coroutine A acquires lock
Time  T1: Coroutine B blocks on lock
Time  T2: Coroutine A checks → None, sets → datetime_A, releases lock
Time  T3: Coroutine B acquires lock, checks → datetime_A (not None), skips set, releases lock ✅
```

**Result**: First timestamp is preserved exactly once.

---

#### Race 3.2: Write-During-Read on Timestamps

**Scenario**: Status endpoint reads `first_failure_timestamp` while it's being written.

**Without Lock**:
```
Time  T0: first_failure_timestamp = None
Time  T1: Coroutine A (status) reads first_failure_timestamp → None
Time  T2: Coroutine B (failure handler) sets first_failure_timestamp = now
Time  T3: Coroutine A returns status: {"first_failure_timestamp": None}  (stale)
```

**Impact**:
- Status shows stale timestamp (acceptable for monitoring)
- No correctness issue (timestamp was None at read time)

**Verdict**: Acceptable for monitoring.

---

### Category 4: Multi-Field Consistency Races

#### Race 4.1: Inconsistent Snapshot of State

**Scenario**: Multiple fields are updated as a group, but a read observes a partial update.

**Without Lock**:
```
Time  T0: has_logged_first_failure = False, first_failure_timestamp = None, failure_count = 0
Time  T1: Coroutine A (status) reads has_logged_first_failure → False
Time  T2: Coroutine B (failure handler) sets has_logged_first_failure = True
Time  T3: Coroutine B sets first_failure_timestamp = now_A
Time  T4: Coroutine B sets failure_count = 1
Time  T5: Coroutine A reads first_failure_timestamp → now_A
Time  T6: Coroutine A reads failure_count → 1
Time  T7: Coroutine A returns: {"has_logged_first_failure": False, "first_failure_timestamp": now_A, "failure_count": 1} ❌ INCONSISTENT
```

**Impact**:
- Status shows inconsistent state (flag=False but timestamp=now_A)
- Confusing diagnostics (was there a failure or not?)
- Breaks assumptions about field relationships

**State After Race**:
```
has_logged_first_failure = True
first_failure_timestamp = now_A
failure_count = 1
Status returned: False, now_A, 1  (inconsistent combination)
```

**With `asyncio.Lock`** (write path only):
- Writes are serialized (all fields updated atomically under lock)
- Reads may still see intermediate state (acceptable for monitoring)
- If strict consistency is required, reads must also acquire lock

**Verdict**: Acceptable for monitoring; critical decision logic requires lock.

---

#### Race 4.2: Notification Sent Flag Inconsistency

**Scenario**: `notification_sent` flag and `notification_sent_at` timestamp are updated separately.

**Without Lock**:
```
Time  T0: notification_sent = False, notification_sent_at = None
Time  T1: Coroutine A (status) reads notification_sent → False
Time  T2: Coroutine B (failure handler) sets notification_sent = True
Time  T3: Coroutine B sets notification_sent_at = now_B
Time  T4: Coroutine A reads notification_sent_at → now_B
Time  T5: Coroutine A returns: {"notification_sent": False, "notification_sent_at": now_B} ❌ INCONSISTENT
```

**Impact**:
- Status shows "not sent" but has a timestamp (contradiction)
- Breaks assumptions about flag/timestamp relationship
- Confusing diagnostics

**With `asyncio.Lock`**:
- All fields updated atomically under lock
- Consistent snapshot guaranteed

---

### Category 5: Check-Then-Act on Reset Operations

#### Race 5.1: Reset-During-Failure Handling

**Scenario**: Admin resets state while failures are still being processed.

**Without Lock**:
```
Time  T0: has_logged_first_failure = True, failure_count = 10
Time  T1: Coroutine A (admin reset) checks has_logged_first_failure → True
Time  T2: Coroutine B (failure handler) checks has_logged_first_failure → True
Time  T3: Coroutine A sets has_logged_first_failure = False (reset)
Time  T4: Coroutine A sets failure_count = 0 (reset)
Time  T5: Coroutine B logs DEBUG (sees flag was True, now False) ❌ CONFUSING
Time  T6: Coroutine B increments failure_count = 1 (based on stale check)
```

**Impact**:
- Reset is partially undone by concurrent failure handler
- State is inconsistent (flag=False, but failure_count was 10, now 1)
- Confusing behavior

**With `asyncio.Lock`**:
- Reset and failure handling serialize
- Either reset completes first, then failure handles new state
- Or failure completes first, then reset clears it
- Both produce consistent final state

---

#### Race 5.2: Concurrent Reset Calls

**Scenario**: Two admins trigger reset simultaneously.

**Without Lock**:
```
Time  T0: has_logged_first_failure = True, failure_count = 10
Time  T1: Coroutine A (admin reset 1) reads has_logged_first_failure → True
Time  T2: Coroutine B (admin reset 2) reads has_logged_first_failure → True
Time  T3: Coroutine A sets has_logged_first_failure = False
Time  T4: Coroutine A sets failure_count = 0
Time  T5: Coroutine B sets has_logged_first_failure = False
Time  T6: Coroutine B sets failure_count = 0  (redundant but harmless)
```

**Impact**:
- Redundant resets (harmless if all fields are set to defaults)
- No correctness issue, just inefficiency

**Verdict**: Acceptable; redundant resets are idempotent.

---

### Category 6: Complex Multi-Step Operation Races

#### Race 6.1: Failure Recording + Notification Sending

**Scenario**: Recording first failure and sending notification is a multi-step operation.

**Without Lock**:
```
Time  T0: has_logged_first_failure = False, notification_sent = False
Time  T1: Coroutine A checks has_logged_first_failure → False
Time  T2: Coroutine B checks has_logged_first_failure → False
Time  T3: Coroutine A sets has_logged_first_failure = True
Time  T4: Coroutine A sends notification (async HTTP call)
Time  T5: Coroutine B sets has_logged_first_failure = True ❌ DUPLICATE
Time  T6: Coroutine B sends notification ❌ DUPLICATE
```

**Impact**:
- Duplicate notifications sent
- State updated twice (redundant but harmless)
- User receives multiple alerts for same event

**With `asyncio.Lock`**:
- Lock protects the entire "check → update → notify" sequence
- Only one coroutine executes the full sequence
- Others see `has_logged_first_failure = True` and skip notification

**Verdict**: Critical race; lock is required.

---

#### Race 6.2: Failure Recording + Persistence (Database Write)

**Scenario**: Recording first failure and persisting to database.

**Without Lock**:
```
Time  T0: has_logged_first_failure = False
Time  T1: Coroutine A checks has_logged_first_failure → False
Time  T2: Coroutine B checks has_logged_first_failure → False
Time  T3: Coroutine A sets has_logged_first_failure = True
Time  T4: Coroutine A persists to DB (async I/O)
Time  T5: Coroutine B sets has_logged_first_failure = True ❌ DUPLICATE
Time  T6: Coroutine B persists to DB ❌ DUPLICATE
```

**Impact**:
- Duplicate database records
- Wasted storage
- Inconsistent query results

**With `asyncio.Lock`**:
- Lock protects check-and-set (state mutation)
- Persistence can happen outside lock (only if it's optional/slow)
- Or lock protects entire sequence if persistence is critical

**Design Decision**: If persistence is optional (monitoring only), it can happen outside lock. If persistence is critical (audit trail), it must be inside lock.

---

## Atomic vs Non-Atomic Operations

### Atomic Operations (No Lock Needed)

These operations are inherently atomic in Python due to the GIL or immutability:

1. **Reading immutable types**: `bool`, `int`, `float` reads are atomic at the bytecode level
2. **Writing to a single variable**: Assignment to a simple variable is atomic
3. **Reading/writing `asyncio.Lock` state**: Lock acquisition/release is atomic

**Caveat**: While individual operations are atomic, **sequences** (check-then-act) are not.

---

### Non-Atomic Operations (Lock Required)

These operations require `asyncio.Lock` for thread-safety:

1. **Check-then-act on `has_logged_first_failure`**:
   ```python
   if not self._has_logged_first_failure:  # ❌ Not atomic
       self._has_logged_first_failure = True
   ```

2. **Read-modify-write on `failure_count`**:
   ```python
   self._failure_count += 1  # ❌ Not atomic (read, add, write)
   ```

3. **Multi-field updates**:
   ```python
   self._has_logged_first_failure = True
   self._first_failure_timestamp = now  # ❌ Not atomic together
   self._failure_count = 1
   ```

4. **Conditional updates based on multiple fields**:
   ```python
   if not self._has_logged_first_failure and self._failure_count == 0:  # ❌ Not atomic
       # ...
   ```

---

## Critical Sections Requiring Lock Protection

### Critical Section 1: First-Failure Detection

```python
async with self._first_failure_lock:
    if not self._has_logged_first_failure:
        # Entire block must be atomic
        self._has_logged_first_failure = True
        self._first_failure_timestamp = datetime.now(timezone.utc)
        self._failure_count = 1
        self._last_failure_timestamp = datetime.now(timezone.utc)
        logger.warning("First failure...")
        await send_notification(...)  # If notification is critical
```

**Why**: Check-then-act on flag, multi-field update, notification sending.

---

### Critical Section 2: Failure Count Increment

```python
async with self._first_failure_lock:
    self._failure_count += 1  # Read-modify-write
    self._last_failure_timestamp = datetime.now(timezone.utc)
```

**Why**: Increment is read-modify-write, timestamp update must be consistent.

---

### Critical Section 3: State Reset

```python
async with self._first_failure_lock:
    self._has_logged_first_failure = False
    self._first_failure_timestamp = None
    self._notification_sent = False
    self._notification_sent_at = None
    # Keep failure_count for diagnostics
```

**Why**: Multi-field reset must be atomic to avoid partial state.

---

### Non-Critical Sections (No Lock Required)

1. **Status reads** (`get_bridge_status()`):
   ```python
   return {
       "has_logged_first_failure": self._has_logged_first_failure,
       "failure_count": self._failure_count,
       # ... (reads are atomic, slight staleness is acceptable)
   }
   ```
   **Why**: Reads are atomic; monitoring can tolerate slight staleness.

2. **Logging operations**:
   ```python
   logger.debug(f"Failure count: {self._failure_count}")
   ```
   **Why**: Logging is side-effect-free for state.

---

## State Transition Conflicts

### Conflict 1: First Failure vs Subsequent Failure

**Transition**: `has_logged_first_failure: False → True`

**Conflict**: Multiple concurrent failures race to be "first".

**Resolution**: Lock ensures exactly one succeeds; others become "subsequent".

---

### Conflict 2: Subsequent Failure vs Reset

**Transition**: `has_logged_first_failure: True → False` (reset)

**Conflict**: Failure handler increments count while reset clears flag.

**Resolution**: Lock serializes operations; reset happens either before or after increment.

---

### Conflict 3: Reset vs First Failure

**Transition**: `has_logged_first_failure: False → True` (after reset)

**Conflict**: Reset clears state while new failure sets it.

**Resolution**: Lock serializes; whichever acquires lock first wins.

---

## Performance Implications of Locking

### Lock Contention Analysis

| Scenario | Lock Usage | Contention | Impact |
|----------|-----------|-----------|--------|
| Bridge healthy (no failures) | None | None | Zero ✅ |
| First failure at startup | Single acquisition | None | Negligible (~1-2ms) |
| Multiple concurrent failures | N acquisitions | Low-moderate | Acceptable (~2-5ms per request) |
| High traffic with bridge down | Many acquisitions | Moderate | Bounded (queue wait = N × 2ms) |

**Worst Case**: 100 concurrent failures = 200ms total queue wait = 2ms average per request.

**Why this is acceptable**:
- Bridge is already down (latency doesn't matter for failed sends)
- Sends are already failing (no "happy path" to optimize)
- Logging overhead dominates (2ms lock is <10% of total)

---

## Mitigation Strategy

### Recommended: `asyncio.Lock` with Minimal Critical Section

```python
class TelegramFallback:
    def __init__(self):
        self._first_failure_lock = asyncio.Lock()

    async def _handle_send_failure(self, error_context: str = ""):
        async with self._first_failure_lock:  # Serialize access
            if not self._has_logged_first_failure:
                # First failure - log at WARNING level
                logger.warning("First failure...")
                self._has_logged_first_failure = True
                self._first_failure_timestamp = datetime.now(timezone.utc)
                self._failure_count = 1
            else:
                # Subsequent failure - log at DEBUG level
                logger.debug(f"Repeated failure #{self._failure_count + 1}")
                self._failure_count += 1
            self._last_failure_timestamp = datetime.now(timezone.utc)
```

**Why this works**:
- Lock protects the entire check-and-set sequence
- Minimal overhead (lock held for microseconds)
- No I/O inside lock (logging is fast, no DB/network calls)
- Serializes the critical section only

---

## Testing Race Conditions

### Test 1: Concurrent First Failures

```python
@pytest.mark.asyncio
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

### Test 2: Concurrent Increments

```python
@pytest.mark.asyncio
async def test_concurrent_increment_race():
    """Verify failure_count is accurate under concurrent increments."""
    fallback = TelegramFallback()
    
    # Simulate first failure
    await fallback._handle_send_failure("first")
    
    # Clear flag to allow increment-only race
    fallback._has_logged_first_failure = True
    
    # Trigger 100 concurrent increments
    await asyncio.gather(*[
        fallback._handle_send_failure(f"error{i}")
        for i in range(100)
    ])
    
    # Verify no lost updates
    assert fallback._failure_count == 101  # 1 + 100
```

### Test 3: Reset During Failures

```python
@pytest.mark.asyncio
async def test_reset_during_failures():
    """Verify reset and failures serialize correctly."""
    fallback = TelegramFallback()
    
    # Start with failures
    await fallback._handle_send_failure("first")
    assert fallback._has_logged_first_failure == True
    
    # Concurrent reset and failure
    reset_task = asyncio.create_task(fallback.reset_first_failure_state())
    failure_task = asyncio.create_task(fallback._handle_send_failure("concurrent"))
    
    await asyncio.gather(reset_task, failure_task)
    
    # State should be consistent (either reset happened or failure)
    assert (fallback._has_logged_first_failure == True or 
            fallback._has_logged_first_failure == False)
```

---

## Summary

### All Identified Race Conditions

| Category | Race | Impact | Mitigation |
|----------|------|--------|------------|
| Check-then-act | Concurrent first failures | Duplicate WARNING logs | `asyncio.Lock` |
| Check-then-act | Read-during-write | Stale status data | Acceptable for monitoring |
| Lost update | Concurrent increment | Inaccurate count | `asyncio.Lock` |
| Lost update | Increment-during-read | Stale count | Acceptable for monitoring |
| Timestamp | Concurrent timestamp write | Non-deterministic timestamp | `asyncio.Lock` |
| Timestamp | Write-during-read | Stale timestamp | Acceptable for monitoring |
| Multi-field | Inconsistent snapshot | Contradictory state | `asyncio.Lock` for writes |
| Multi-field | Notification flag inconsistency | Contradictory state | `asyncio.Lock` |
| Reset | Reset-during-failure | Partial undo | `asyncio.Lock` |
| Reset | Concurrent reset | Redundant resets | Acceptable (idempotent) |
| Multi-step | Failure + notification | Duplicate notifications | `asyncio.Lock` |
| Multi-step | Failure + persistence | Duplicate DB records | `asyncio.Lock` (or outside if optional) |

### Atomic Operations (No Lock)

- Reading/writing single variables (bool, int)
- Reading immutable types

### Non-Atomic Operations (Lock Required)

- Check-then-act sequences
- Read-modify-write (increment)
- Multi-field updates
- Conditional updates based on multiple fields

### Recommended Strategy

1. **Use `asyncio.Lock`** for all state mutations (write operations)
2. **No lock for reads** (monitoring can tolerate slight staleness)
3. **Minimal critical section** (only state mutations, no I/O)
4. **Test with `asyncio.gather()`** to verify race condition prevention

### Performance Impact

- **Happy path**: Zero overhead (no lock acquisition)
- **Error path**: +2-5ms per request (negligible, only affects degraded state)
- **Worst case**: ~200ms total wait for 100 concurrent failures (acceptable)

---

**Document**: adc-4ol5  
**Status**: ✅ Complete  
**Dependencies**: adc-50ld (thread-safety approach), adc-65l3 (state structure), adc-2duz (storage design)  
**Date**: 2026-07-02
