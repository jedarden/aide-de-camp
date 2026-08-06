# First-Failure Tracking Design (adc-4vhr)

## Overview
Design for tracking and detecting the FIRST Telegram send failure after startup in aide-de-camp (async FastAPI application).

## Current Implementation Analysis

### State Storage (Module-level Singleton)

State is stored as instance variables on the `TelegramFallback` singleton in `src/telegram/fallback.py`:

```python
# Lines 86-98 in fallback.py
self._has_logged_first_failure: bool = False           # Claim flag
self._failure_count: int = 0                           # Total failures
self._first_failure_timestamp: Optional[datetime] = None   # Set-once
self._last_failure_timestamp: Optional[datetime] = None   # Updated every failure
self._seen_failure_types: set[str] = set()             # Per-type dedup
self._last_repeated_log_timestamp: Optional[datetime] = None   # Rate-limit tracking
self._failures_since_last_log: int = 0                 # Dedup counter
```

**Key Design Decision:** State lives on the singleton instance, not in the database. This is intentional — first-failure tracking is a per-startup diagnostic, not durable state. A process restart re-arms detection automatically.

### Thread-Safety Mechanism

Asyncio lock serializes the critical section:

```python
# Line 110 in fallback.py
self._first_failure_lock: asyncio.Lock = asyncio.Lock()

# Lines 329-330: Entry point from send_message failures
async def _handle_send_failure(self, error, error_context):
    async with self._first_failure_lock:
        self._record_failure_locked(error=error, error_context=error_context)
```

**Why asyncio.Lock?** 
- ADC is async FastAPI — multiple coroutines can call `send_message` concurrently
- Lock ensures the read-then-set of `_has_logged_first_failure` cannot be interleaved
- Only ONE coroutine wins the claim to become "first failure"

**Critical Section Design** (lines 343-441):
```python
def _record_failure_locked(self, error, error_context) -> bool:
    """Caller MUST hold _first_failure_lock. Sync on purpose — no await."""
    now = datetime.now()
    self._failure_count += 1
    self._last_failure_timestamp = now
    self._failures_since_last_log += 1

    # The CLAIM: check-and-set under lock
    if not self._has_logged_first_failure:
        self._has_logged_first_failure = True          # Irreversible transition
        self._first_failure_timestamp = now
        # ... log WARNING ...
        return True  # Winner of the claim

    # Subsequent failures reach here
    return False
```

**Why synchronous inside the lock?** No `await` in the critical section. This prevents coroutine switching while holding the lock, avoiding deadlock and minimizing lock contention.

### First-Failure Detection Logic

**Claim Pattern (Lines 390-408):**
1. Check `_has_logged_first_failure` flag
2. If False → claim it (set to True), log WARNING, return True
3. If True → skip claim, return False

**Per-Failure-Type Dedup (adc-15u0, Lines 388-426):**
- New failure types are logged immediately and independently
- `_seen_failure_types: set[str]` tracks which types have been seen
- A different failure type is never swallowed by the ongoing-outage cooldown

**Rate-Limiting for Repeated Failures (Lines 332-441):**
- After first failure, same-type failures are rate-limited
- One DEBUG summary per `_failure_log_interval_seconds` window (default: 300s)
- Failures inside window are counted silently (`_failures_since_last_log`)
- Prevents log spam during sustained outages

### Why This Design Works

1. **Single Process Model:** ADC runs as a single FastAPI process (one `uvicorn` worker). No cross-process state sharing needed.

2. **Process Restart = Automatic Re-arm:** Since state is in-memory only, a process restart automatically resets all flags. No manual reset needed for deployments.

3. **Lock-Free Status Reads:** `get_status()` method (lines 267-308) performs lock-free reads. Monitoring tolerates momentary staleness — better than blocking status queries on the failure lock.

4. **Clear Winner Semantics:** The claim-and-set pattern guarantees exactly one WARNING per process startup, even if 100 concurrent `send_message` calls fail simultaneously.

## Implementation Guidance

### For Adding First-Failure Tracking to New Components

When implementing first-failure tracking for a new component:

1. **State Storage:**
   ```python
   class YourComponent:
       def __init__(self):
           self._has_logged_first_failure = False
           self._first_failure_lock = asyncio.Lock()
   ```

2. **Thread-Safe Claim:**
   ```python
   async def _handle_failure(self, error):
       async with self._first_failure_lock:
           if not self._has_logged_first_failure:
               self._has_logged_first_failure = True
               logger.warning(f"First failure detected: {error}")
               # Additional first-failure actions (metrics, alerts, etc.)
   ```

3. **Call from Failure Paths:**
   ```python
   async def send_request(self):
       try:
           # ... send request ...
       except Exception as e:
           await self._handle_failure(e)
           return False
   ```

4. **Consider Per-Type Dedup (Optional):**
   - If your component has multiple failure modes (network, auth, parse)
   - Track `_seen_failure_types: set[str]`
   - Log new failure types immediately and independently

5. **Add Status Endpoint (Optional):**
   ```python
   def get_status(self) -> dict:
       return {
           "has_logged_first_failure": self._has_logged_first_failure,
           "failure_count": self._failure_count,
       }
   ```

### Race Condition Handling

**Scenario:** Two coroutines hit a failure simultaneously

```
Coroutine A: acquires lock → checks flag (False) → sets flag (True) → logs WARNING → releases lock → returns True
Coroutine B: blocked on lock → acquires lock → checks flag (True) → skips claim → releases lock → returns False
```

**Guarantee:** Exactly one WARNING is logged. Coroutine A wins the claim; Coroutine B sees the flag is already True and does nothing.

### Reset Mechanism

**Manual Reset (for testing):**
```python
async def reset_first_failure_state(self) -> None:
    """Re-arm first-failure detection. Used by tests."""
    async with self._first_failure_lock:
        self._has_logged_first_failure = False
        self._first_failure_timestamp = None
```

**Automatic Reset:** Process restart (deployment, crash, manual restart) — all in-memory state is lost, flags reset to initial values.

## Acceptance Criteria Status

- ✅ **Design documented in bead body** — This document
- ✅ **Explains state storage** — Module-level singleton instance variables
- ✅ **Explains initialization** — Constructor sets initial values (`False`, `0`, `None`, `set()`)
- ✅ **Explains race-condition handling** — asyncio.Lock serializes claim; critical section has no await
- ✅ **Clear implementation guidance** — Step-by-step pattern for new components above
- ✅ **Subsequent failures don't re-trigger** — Claim-and-set pattern guarantees exactly one WARNING per startup

## Related Files

- `src/telegram/fallback.py` — Lines 86-110 (state declaration), 329-441 (failure handling)
- `src/main.py` — Lines 157-169 (startup health check)
- `/api/v1/status/telegram` endpoint — Exposes first-failure state via `get_status()`

## Testing Guidance

**Unit Test Pattern:**
```python
async def test_first_failure_claim():
    component = YourComponent()
    assert component._has_logged_first_failure == False

    # Simulate concurrent failures
    tasks = [component._handle_failure(Exception("fail")) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # Exactly one should return True (the claim winner)
    assert sum(results) == 1
    assert component._has_logged_first_failure == True
```

**Integration Test Pattern:**
```python
async def test_reset_after_restart():
    # Before "restart"
    component = YourComponent()
    await component._handle_failure(Exception("fail"))
    assert component._has_logged_first_failure == True

    # Simulate restart (recreate instance)
    component = YourComponent()
    assert component._has_logged_first_failure == False  # Re-armed
```

## Conclusion

The current implementation in `TelegramFallback` is production-ready and demonstrates all required patterns:
- In-memory state on singleton instance
- asyncio.Lock for thread-safe claim
- Check-and-set under lock prevents race conditions
- Per-failure-type dedup for visibility
- Rate-limiting prevents log spam
- Process restart = automatic re-arm

Use this as a reference pattern when implementing first-failure tracking in other components.
