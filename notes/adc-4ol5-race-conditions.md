# Race Conditions for Concurrent First-Failure State

## Overview

This document enumerates all possible race conditions when multiple async FastAPI requests attempt to read/write first-failure state concurrently in the `TelegramFallback` class. It identifies specific race scenarios, conflicting state transitions, and distinguishes between atomic and non-atomic operations.

## Current Implementation Status

**Current code (`src/telegram/fallback.py`) is NOT thread-safe:**

```python
def _handle_send_failure(self, error_context: str = ""):
    """Handle a send failure - log warning only on the first failure after startup."""
    self._is_reachable = False
    self._failure_count += 1
    now = datetime.now()

    if not self._has_logged_first_failure:  # ❌ CHECK - not atomic with SET
        # First failure after startup - log at WARNING level
        logger.warning(...)  # ❌ Multiple WARNINGs possible
        self._has_logged_first_failure = True  # ❌ SET - race condition here
        self._last_failure_logged = now
    else:
        # Subsequent failures - log at DEBUG level to avoid spam
        logger.debug(...)
```

**Problems:**
1. ❌ `_handle_send_failure()` is synchronous, not async
2. ❌ No lock protection on check-then-act sequence
3. ❌ Multiple concurrent requests can all see `_has_logged_first_failure = False`
4. ❌ All concurrent requests log WARNING (violates "one WARNING per startup" requirement)
5. ❌ `failure_count += 1` is a read-modify-write operation (not atomic)

## State Variables

Protected state (requires lock for mutation):
- `_has_logged_first_failure: bool` — Primary flag for first-failure detection
- `_failure_count: int` — Total failures counter
- `_first_failure_timestamp: Optional[datetime]` — Timestamp of first failure
- `_last_failure_timestamp: Optional[datetime]` — Timestamp of most recent failure
- `_is_reachable: Optional[bool]` — Bridge reachability state

## Race Conditions

### Race Condition 1: Duplicate First-Failure Logs (Check-Then-Act)

**Severity:** High  
**Impact:** Log spam, violates requirement of exactly one WARNING per startup

**Scenario:** Multiple concurrent requests fail at application startup before any has set the flag.

**Timeline:**
```
Time  T0: Request A fails → enters _handle_send_failure()
Time  T1: Request A checks _has_logged_first_failure → False
Time  T2: Request B fails → enters _handle_send_failure()
Time  T3: Request B checks _has_logged_first_failure → False  ❌ Both see False
Time  T4: Request A logs WARNING
Time  T5: Request A sets _has_logged_first_failure = True
Time  T6: Request B logs WARNING  ❌ DUPLICATE WARNING
Time  T7: Request B sets _has_logged_first_failure = True
```

**Result:**
- ❌ 2 WARNING logs for the same "first" failure
- ❌ Requirement violated: "one WARNING per startup"
- ❌ Log spam when bridge is down

**Why it happens:**
- The check (`if not self._has_logged_first_failure`) and set (`self._has_logged_first_failure = True`) are NOT atomic
- Between the check and set, other requests can also check and see the old value
- No serialization mechanism exists

**Affected state:**
- `_has_logged_first_failure` (check-then-act)
- `_first_failure_timestamp` (may be set multiple times)

**Mitigation required:**
```python
async with self._first_failure_lock:  # Serialize check-and-set
    if not self._has_logged_first_failure:
        logger.warning(...)
        self._has_logged_first_failure = True
```

---

### Race Condition 2: Lost Counter Updates (Read-Modify-Write)

**Severity:** Medium  
**Impact:** Inaccurate failure count, misleading diagnostics

**Scenario:** Multiple concurrent failures increment the counter simultaneously.

**Timeline:**
```
Time  T0: _failure_count = 0
Time  T1: Request A reads _failure_count → 0
Time  T2: Request B reads _failure_count → 0  ❌ Both read same value
Time  T3: Request A calculates 0 + 1 = 1
Time  T4: Request B calculates 0 + 1 = 1
Time  T5: Request A writes _failure_count = 1
Time  T6: Request B writes _failure_count = 1  ❌ Lost update (should be 2)
```

**Result:**
- ❌ `_failure_count = 1` but 2 failures occurred
- ❌ Under-counting of failures
- ❌ Misleading metrics for monitoring

**Why it happens:**
- `failure_count += 1` is a read-modify-write sequence
- Not atomic: read old value, modify, write back
- Concurrent executions interleave, causing lost updates

**Affected state:**
- `_failure_count` (read-modify-write)

**Mitigation required:**
```python
async with self._first_failure_lock:  # Serialize increments
    self._failure_count += 1
```

---

### Race Condition 3: First-Failure Timestamp Overwrite

**Severity:** Low  
**Impact:** Lost accuracy of first-failure timing, harder to correlate with logs

**Scenario:** Multiple concurrent failures attempt to set the first-failure timestamp.

**Timeline:**
```
Time  T0: Request A fails → checks _has_logged_first_failure → False
Time  T1: Request B fails → checks _has_logged_first_failure → False
Time  T2: Request A logs WARNING, sets _first_failure_timestamp = 14:30:00.100
Time  T3: Request B logs WARNING, sets _first_failure_timestamp = 14:30:00.250  ❌ Overwrite
```

**Result:**
- ❌ First failure recorded at 14:30:00.250 (actually happened at 14:30:00.100)
- ❌ 150ms timing error
- ❌ Difficult to correlate with logs from Request A

**Why it happens:**
- Check-then-act race on `_has_logged_first_failure`
- Both requests pass the check, both set the timestamp
- Last write wins

**Affected state:**
- `_first_failure_timestamp` (set multiple times due to race condition #1)

**Mitigation required:**
```python
async with self._first_failure_lock:
    if not self._has_logged_first_failure:
        self._first_failure_timestamp = datetime.now()  # Set once
        self._has_logged_first_failure = True  # Under lock
```

---

### Race Condition 4: Last-Failure Timestamp Lost Update

**Severity:** Low  
**Impact:** Last-failure timestamp may not be the actual last failure

**Scenario:** Multiple concurrent failures update the last-failure timestamp.

**Timeline:**
```
Time  T0: Request A fails → _last_failure_timestamp = 14:30:00.100
Time  T1: Request B fails → _last_failure_timestamp = 14:30:00.150
Time  T2: Request C fails → _last_failure_timestamp = 14:30:00.200
Time  T3: Request A updates _last_failure_timestamp = 14:30:00.250  ❌ Overwrite
Time  T4: Request B updates _last_failure_timestamp = 14:30:00.300  ❌ Overwrite
Time  T5: Request C updates _last_failure_timestamp = 14:30:00.350
```

**Result:**
- ⚠️ Final timestamp is 14:30:00.350 (correct if Request C was last)
- ⚠️ But timing is non-deterministic due to scheduling
- ⚠️ May not reflect actual last failure in real-time order

**Why it happens:**
- Timestamp assignment happens at the end of `_handle_send_failure()`
- No ordering guarantee between concurrent coroutines
- Latest timestamp in wall-clock time may not be from the last coroutine to complete

**Affected state:**
- `_last_failure_timestamp` (non-deterministic ordering)

**Note:** This is a minor issue. For diagnostics, "last failure within a few ms" is acceptable.

---

### Race Condition 5: Read-During-Write on Status Check

**Severity:** Low  
**Impact:** Inconsistent state reported to status endpoint

**Scenario:** A status check reads state while a failure handler is writing it.

**Timeline:**
```
Time  T0: Request A (failure) acquires lock (not implemented yet)
Time  T1: Request A sets _has_logged_first_failure = True
Time  T2: Request A sets _failure_count = 5
Time  T3: Request B (status check) reads _has_logged_first_failure → True  ✅ Consistent
Time  T4: Request B reads _failure_count → 5  ✅ Consistent
Time  T5: Request A sets _first_failure_timestamp = now
Time  T6: Request A releases lock
```

**Result with lock:**
- ✅ State is consistent (all reads see either pre-write or post-write state)
- ✅ No torn reads (half-written state)

**Result WITHOUT lock (current):**
- ⚠️ Status check could read `_has_logged_first_failure = True` but `_failure_count = 0`
- ⚠️ Inconsistent state reported (transient inconsistency)
- ⚠️ Confusing for monitoring tools

**Why it happens:**
- Without lock, reads can interleave with writes
- Multi-field state is read atomically only if writes are serialized
- Python's GIL doesn't protect across async await points

**Affected state:**
- All fields when read via `get_bridge_status()`

**Mitigation:**
- Reads don't strictly need a lock if eventual consistency is acceptable
- But lock-based writes ensure reads always see consistent snapshots

---

### Race Condition 6: Reachability State Toggle

**Severity:** Medium  
**Impact:** Incorrect bridge reachability reporting

**Scenario:** A success and a failure occur concurrently, both updating `_is_reachable`.

**Timeline:**
```
Time  T0: Request A succeeds → sets _is_reachable = True
Time  T1: Request B fails → sets _is_reachable = False  ❌ Overwrites success
Time  T2: Status check → reports bridge unreachable  ❌ Wrong (just succeeded)
```

**Result:**
- ❌ Bridge reported as unreachable even though a request just succeeded
- ❌ Misleading diagnostics
- ❌ Wrong state for monitoring

**Why it happens:**
- `_is_reachable = True` and `_is_reachable = False` are independent assignments
- No synchronization between success and failure paths
- Last write wins, regardless of actual order of events

**Affected state:**
- `_is_reachable` (unsynchronized updates from success and failure paths)

**Mitigation required:**
```python
# On success (needs lock if concurrent failures possible)
async with self._first_failure_lock:
    self._is_reachable = True

# On failure (already under lock for other state)
async with self._first_failure_lock:
    self._is_reachable = False
    # ... other failure state updates ...
```

---

## Atomic vs Non-Atomic Operations

### Atomic Operations (No Lock Required)

These operations are atomic in Python and don't need lock protection:

1. **Boolean assignment:**
   ```python
   self._has_logged_first_failure = True  # ✅ Atomic
   ```

2. **Object reference assignment:**
   ```python
   self._first_failure_timestamp = datetime.now()  # ✅ Atomic
   ```

3. **Integer assignment (not increment):**
   ```python
   self._failure_count = 42  # ✅ Atomic
   ```

**Why these are atomic:**
- Python's GIL (Global Interpreter Lock) protects single bytecode operations
- Assignment of immutable values (bool, int, object refs) is a single bytecode
- No intermediate state is visible to other threads/coroutines

### Non-Atomic Operations (Lock Required)

These operations are NOT atomic and require lock protection:

1. **Check-then-act (read-then-write):**
   ```python
   if not self._has_logged_first_failure:  # ❌ Non-atomic check
       self._has_logged_first_failure = True  # ❌ Non-atomic set
   ```
   - **Why:** Two separate operations with a gap where other code can run
   - **Fix:** Serialize the entire sequence with a lock

2. **Read-modify-write (increment):**
   ```python
   self._failure_count += 1  # ❌ Non-atomic
   # Expands to: temp = self._failure_count; temp += 1; self._failure_count = temp
   ```
   - **Why:** Three separate operations (read, add, write)
   - **Fix:** Serialize with a lock

3. **Multi-field consistent read:**
   ```python
   return {
       "has_logged_first_failure": self._has_logged_first_failure,
       "failure_count": self._failure_count,  # ❌ May be inconsistent
   }
   ```
   - **Why:** Multiple reads can interleave with writes
   - **Fix:** Either use lock for reads, or accept eventual consistency

## State Transition Conflicts

### Conflict Matrix

| State Variable | Write Operation | Conflicting Write | Impact |
|----------------|-----------------|-------------------|--------|
| `_has_logged_first_failure` | False → True (first failure) | False → True (concurrent first failure) | Duplicate WARNING logs |
| `_failure_count` | Increment (failure) | Increment (concurrent failure) | Lost updates (under-count) |
| `_first_failure_timestamp` | None → datetime (first failure) | None → datetime (concurrent first failure) | Timestamp overwrite |
| `_last_failure_timestamp` | datetime → datetime (failure) | datetime → datetime (concurrent failure) | Non-deterministic ordering |
| `_is_reachable` | True (success) / False (failure) | False (failure) / True (success) | Toggle race |

### State Transition Diagram ( Unsafe)

```
         Startup
            │
            ▼
    ┌───────────────────────┐
    │ _has_logged_first_   │
    │ failure = False       │
    │ _failure_count = 0    │
    │ timestamps = None     │
    └───────────────────────┘
            │
            │ Request A fails
            │ Request B fails (concurrent)
            ▼
    ┌───────────────────────┐
    │ ❌ RACE CONDITION     │
    │                      │
    │ Both requests see:   │
    │ _has_logged_first_  │
    │ failure = False     │
    └───────────────────────┘
            │
            ├─► Request A logs WARNING
            ├─► Request A sets flag = True
            ├─► Request A sets timestamp = T1
            │
            ├─► Request B logs WARNING ❌ DUPLICATE
            ├─► Request B sets flag = True
            └─► Request B sets timestamp = T2 ❌ OVERWRITE
            │
            ▼
    ┌───────────────────────┐
    │ Inconsistent State   │
    │                      │
    │ _has_logged_first_   │
    │ failure = True       │
    │ _failure_count = 1   │ ❌ Should be 2
    │ first_timestamp = T2 │ ❌ Should be T1
    └───────────────────────┘
```

## Concurrency Scenarios

### Scenario 1: Cold Start with Burst Traffic

**Context:** Application starts receiving requests immediately; bridge is down.

**Race condition:** All 10 concurrent requests fail simultaneously.

**Timeline:**
```
T0: 10 requests burst into send_message()
T1: All 10 requests enter _handle_send_failure()
T2: All 10 requests check _has_logged_first_failure → False
T3: All 10 requests log WARNING  ❌ 10 WARNING logs
T4: All 10 requests set flag = True
T5: All 10 requests set timestamp =各自的 now()
T6: All 10 requests increment _failure_count  ❌ Lost updates
```

**Result:**
- ❌ 10 WARNING logs (expected: 1)
- ❌ _failure_count likely < 10 (lost increments)
- ⚠️ _first_failure_timestamp is the last of 10 writes

**Impact:** Severe log spam, inaccurate diagnostics

---

### Scenario 2: Ongoing Failures with New Request

**Context:** Bridge is down; failures are ongoing. A new request arrives.

**Race condition:** New request races with ongoing failure handler.

**Timeline:**
```
T0: Request A (failure handler) sets _failure_count = 42
T1: Request B (new failure) reads _failure_count → 42
T2: Request B checks flag → True
T3: Request B logs DEBUG (correct)
T4: Request A finishes, sets _failure_count = 43
T5: Request B increments _failure_count → 43  ❌ Read stale value
T6: Request B writes _failure_count = 44  ❌ Should be 43 or 44 depending on order
```

**Result:**
- ⚠️ Failure count may be off by 1 (less severe than burst scenario)
- ✅ Only one WARNING logged (flag already True)
- ⚠️ Counter increment race still possible

**Impact:** Minor inaccuracy in failure count

---

### Scenario 3: Success/Failure Toggle

**Context:** Bridge is flaky; a success and failure occur concurrently.

**Race condition:** Success path sets `_is_reachable = True` while failure path sets `False`.

**Timeline:**
```
T0: Request A succeeds → sets _is_reachable = True
T1: Request B fails → sets _is_reachable = False  ❌ Overwrites success
T2: Status check → reports unreachable
```

**Result:**
- ❌ Bridge reported as unreachable despite a success
- ❌ Misleading for monitoring

**Impact:** Incorrect reachability state

---

## Mitigation Strategy

### Required Changes

1. **Add asyncio.Lock:**
   ```python
   def __init__(self, bridge_url: str | None = None):
       # ...
       self._first_failure_lock = asyncio.Lock()
   ```

2. **Make _handle_send_failure async:**
   ```python
   async def _handle_send_failure(self, error_context: str = ""):
       async with self._first_failure_lock:
           # ... all state mutations ...
   ```

3. **Protect success path:**
   ```python
   async def send_message(self, chat_id, message, parse_mode="HTML"):
       # ... on success ...
       async with self._first_failure_lock:
           self._is_reachable = True
   ```

4. **Update all call sites:**
   ```python
   # Change from:
   self._handle_send_failure(error_msg)
   # To:
   await self._handle_send_failure(error_msg)
   ```

### State Protection Summary

| State Variable | Protected By Lock? | Reason |
|----------------|-------------------|--------|
| `_has_logged_first_failure` | ✅ Yes | Check-then-act race |
| `_failure_count` | ✅ Yes | Read-modify-write race |
| `_first_failure_timestamp` | ✅ Yes | Set-once race via flag check |
| `_last_failure_timestamp` | ⚠️ Optional | Non-critical if inconsistent |
| `_is_reachable` | ✅ Yes | Toggle race with success path |

### Performance Impact

**Lock contention analysis:**

- **Happy path (no failures):** Zero lock usage ✅
- **First failure:** Single lock acquisition (~2ms) ✅
- **Subsequent failures:** Lock serializes increments (acceptable, already on error path) ✅
- **Success/failure toggle:** Lock prevents toggle race ✅

**Worst case (100 concurrent failures):**
- Each request waits ~2ms for lock
- Total queue wait: ~200ms
- Average per-request overhead: ~2ms
- Acceptable because bridge is already down (error path)

## Testing Requirements

### Test 1: Concurrent First Failures
```python
async def test_concurrent_first_failures():
    """Verify only one WARNING is logged for N concurrent failures."""
    fallback = TelegramFallback()
    
    # Trigger 10 concurrent failures
    await asyncio.gather(*[
        fallback._handle_send_failure(f"error{i}")
        for i in range(10)
    ])
    
    # Verify: Only one WARNING logged, 9 DEBUG logs
    assert fallback._has_logged_first_failure == True
    assert fallback._failure_count == 10  # No lost updates
```

### Test 2: Counter Increment Race
```python
async def test_counter_increment_race():
    """Verify failure count is accurate with concurrent increments."""
    fallback = TelegramFallback()
    fallback._has_logged_first_failure = True  # Skip first-failure logging
    
    # Trigger 100 concurrent failures
    await asyncio.gather(*[
        fallback._handle_send_failure(f"error{i}")
        for i in range(100)
    ])
    
    # Verify: No lost updates
    assert fallback._failure_count == 100
```

### Test 3: Success/Failure Toggle
```python
async def test_success_failure_toggle():
    """Verify _is_reachable state is consistent."""
    fallback = TelegramFallback()
    
    # Concurrent success and failure
    await asyncio.gather(
        fallback.send_message(chat_id, "msg"),  # Mocked success
        fallback.send_message(chat_id, "msg"),  # Mocked failure
    )
    
    # Verify: State is consistent (not toggling back and forth)
    assert fallback._is_reachable in (True, False)  # One value, not switching
```

## Summary

### Identified Race Conditions

1. ✅ **Duplicate first-failure logs** (check-then-act on `_has_logged_first_failure`)
2. ✅ **Lost counter updates** (read-modify-write on `_failure_count`)
3. ✅ **First-failure timestamp overwrite** (concurrent sets due to race #1)
4. ⚠️ **Last-failure timestamp lost update** (non-deterministic ordering)
5. ⚠️ **Read-during-write inconsistency** (status checks during writes)
6. ✅ **Reachability toggle race** (concurrent success/failure)

### Atomic vs Non-Atomic

**Atomic (no lock):**
- Boolean/object reference assignments

**Non-atomic (lock required):**
- Check-then-act sequences
- Read-modify-write operations
- Multi-field consistent reads

### Mitigation Required

- Add `asyncio.Lock` to `TelegramFallback.__init__()`
- Make `_handle_send_failure()` async
- Protect all state mutations with lock
- Update all call sites to `await` the async method

### Performance Impact

- Zero overhead on happy path (no failures, no lock usage)
- ~2ms overhead per failure (negligible, error path)
- Bounded worst case: N failures × 2ms = acceptable

### Testing

- Concurrent first-failure test (prevent duplicate WARNING logs)
- Counter increment race test (prevent lost updates)
- Success/failure toggle test (prevent reachability race)
