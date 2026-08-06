# First-Failure Detection Logic Design

**Bead:** adc-12bt — "Design first-failure detection logic"
**Child of:** adc-4vhr (Design first-failure tracking mechanism)
**Status:** Complete
**Date:** 2026-08-06

## Overview

This document specifies **HOW** to detect the first Telegram send failure versus subsequent failures, triggering notification exactly once per process startup. The detection is reactive (after failure) and uses a claim-and-set pattern to ensure exactly-once notification under concurrency.

---

## 1. Detection Timing: When to Check

### Decision: Reactive-Only (After Failure, Not Before Send)

Detection occurs **only after a real send failure**, not proactively before attempting sends.

**Why reactive-only:**

1. **Avoids false positives.** A pre-send health check would fail during transient outages even if the actual send would succeed (race condition).
2. **Minimizes overhead.** No redundant health-check calls before every send; we only react to actual failures.
3. **Simpler state model.** One trigger point (failure path) instead of two (pre-send check + failure handler).
4. **Matches the semantic.** "First send failure" means a send actually failed, not that we predict it will fail.

**What we DON'T do (proactive approaches rejected):**

- ❌ Pre-send health check (`check_bridge_available()`) before each `send_message()` call
- ❌ Separate "bridge down" detection thread polling independently
- ❌ Timeout-based prediction (if health check takes > N seconds, mark as failed)

**What we DO (reactive approach):**

The moment `send_message()` encounters any of these failure modes:
- HTTP non-2xx response (4xx, 5xx, etc.)
- `httpx.RequestError` (network error, timeout, connection refused)
- Any other `Exception` during the send

...we trigger `_handle_send_failure()` which performs the first-failure detection.

**Note:** The lifespan startup runs `check_bridge_available()` once at boot for `/health` status only, NOT for first-failure detection. That's a separate health-reporting concern.

---

## 2. Detection Logic: The Check Algorithm

### Core Principle: Claim-and-Set with Boolean Flag

The detection logic is a simple **read-then-write** pattern protected by a lock:

```python
# Pseudo-code inside the locked section
if not self._has_logged_first_failure:
    self._has_logged_first_failure = True
    # This is the first failure
    return True  # Triggers notification
else:
    # Already failed before
    return False  # Suppress notification
```

### What Makes a Failure "First"?

**"First" is defined by the claim, not by timestamp.**

- The first coroutine to acquire the lock, observe `_has_logged_first_failure == False`, and flip it to `True` is "the first failure."
- All subsequent coroutines see `True` and return `False` (subsequent failures).
- This is a **claim-and-set** pattern, not a timestamp comparison.

**Why not timestamp-based?**

- Timestamp comparisons require sorting multiple failure timestamps and defining "first" as `min(timestamps)`.
- That's more complex and requires storing all failure timestamps or a running minimum.
- The claim-and-set pattern gives us a clear winner with O(1) state (one boolean).

### Complete Detection Flow

```
send_message() attempts to send to Telegram bridge
  │
  ├─ SUCCESS (HTTP 200)
  │  → _is_reachable = True
  │  → return True
  │  └─ (no detection involvement)
  │
  └─ FAILURE (non-2xx | RequestError | Exception)
       ↓
     await _handle_send_failure(error_context)
       │
       ├─ Acquire lock: async with self._first_failure_lock:
       │    │
       │    └─ Call _record_failure_locked(error_context)
       │         │
       │         ├─ Unconditional state updates:
       │         │  - _is_reachable = False
       │         │  - _failure_count += 1
       │         │  - _last_failure_timestamp = now
       │         │
       │         ├─ if not _has_logged_first_failure:  # ← THE CHECK
       │         │      self._has_logged_first_failure = True  # ← THE CLAIM
       │         │      self._first_failure_timestamp = now
       │         │      logger.warning("First Telegram send failure...")
       │         │      return True  # "was_first" signal
       │         │
       │         └─ else:
       │              logger.debug(f"Repeated failure #{_failure_count}...")
       │              return False  # "was_first=False" signal
       │
       └─ Release lock
            │
            └─ if was_first:
                 await _notify_first_failure(error_context)
                 # Side-channel notification (NOT send_message)
```

### Key Points

1. **The check happens inside the lock.** No other coroutine can flip the flag between the read and the write.
2. **The check is a simple boolean comparison.** `if not self._has_logged_first_failure` is all we need.
3. **The flip is atomic with the check.** Under the lock, the read-then-write is one indivisible operation.
4. **We return a signal (`was_first`).** The locked helper returns `True`/`False` to indicate whether this call was the first, so the caller can decide whether to notify.
5. **Notification runs AFTER the lock releases.** The expensive I/O (`_notify_first_failure`) happens outside the lock to avoid holding it during slow operations.

---

## 3. Why Subsequent Failures Are Ignored

### Mechanism: Boolean Flag Latch

Once `_has_logged_first_failure` is set to `True`:

1. **All future failures see `True`** in the `if not self._has_logged_first_failure` check.
2. **They return `False`** from `_record_failure_locked`, indicating "not the first."
3. **The caller skips `await _notify_first_failure()`** because `was_first == False`.
4. **They only log at DEBUG level** with the failure count.

### No Reset Window (Per-Startup Semantic)

The flag is **never reset** during the process lifetime. It only resets on:
- Process restart (new `TelegramFallback()` instance created)
- Explicit call to `reset_first_failure_state()` (test hook or future recovery-based reset)

**Why no time-based reset?**

- A time-based cooldown (e.g., "re-notify after 5 minutes of failures") would require tracking:
  - Time of first failure
  - Time of last failure
  - A timer or comparison on every failure
- The per-startup semantic is simpler: **one notification per process lifetime.**
- If the bridge stays down across restarts, each restart correctly logs one WARNING.
- Future extension: recovery-based reset (after N consecutive successes) can re-arm detection.

### What Subsequent Failures Still Do

Even though they're "ignored" for notification purposes, subsequent failures:
1. **Increment `_failure_count`.** Diagnostic: total failures since startup.
2. **Update `_last_failure_timestamp`.** "Last failed X seconds ago."
3. **Log at DEBUG level.** Visible in logs but not spammy.

This means we still have full observability of ongoing failures, just without repeated notifications.

---

## 4. Concurrency: Exactly One Notification Under Race Conditions

### Scenario: N Simultaneous Failures

When N coroutines all hit `_handle_send_failure()` at the same time (e.g., a burst of dispatches to a dead bridge):

```
Coroutine 1                Coroutine 2                ...  Coroutine N
     │                          │                          │
     ├─ await lock              ├─ await lock              ├─ await lock
     │  (blocks)                │  (blocks)                │  (blocks)
     │                          │                          │
  [acquires lock]               │                          │
     │                          │                          │
     ├─ _has_logged... = False  │                          │
     ├─ Flip to True            │                          │
     ├─ Log WARNING              │                          │
     └─ return True             │                          │
  [releases lock]               │                          │
                                │  [acquires lock]         │
                                │                          │
                                ├─ _has_logged... = True   │
                                ├─ (already flipped)       │
                                ├─ Log DEBUG               │
                                └─ return False            │
                             [releases lock]              │
                                                          │
                                                       [acquires lock]
                                                          │
                                                          ├─ _has_logged... = True
                                                          ├─ Log DEBUG
                                                          └─ return False
                                                       [releases lock]
```

**Result:**
- Exactly **one** WARNING log (from Coroutine 1)
- Exactly **one** `_notify_first_failure()` call (from Coroutine 1)
- **N** entries in `_failure_count` (each coroutine increments it)
- **One** `_first_failure_timestamp` (set by Coroutine 1)
- **One** `_last_failure_timestamp` (set by the last coroutine to finish)

### Why This Works

1. **The lock serializes access.** Only one coroutine at a time can be in `_record_failure_locked`.
2. **The flip is atomic with the check.** Under the lock, no other coroutine can interleave a read between the `if` and the assignment.
3. **The first coroutine wins.** The first to acquire the lock sees `False`, flips to `True`, and returns `True`.
4. **All others lose.** Subsequent coroutines see `True` (already flipped) and return `False`.

### Edge Case: Lock-Free Optimizations?

**Could we skip the lock and rely on CPython's GIL?**

- In the current code, `_handle_send_failure` is synchronous and await-free.
- In CPython, the GIL ensures only one thread executes Python bytecode at a time.
- asyncio switches tasks only at `await` points, so a sync function is atomic w.r.t. other coroutines.

**BUT:** The moment someone adds an `await` inside the critical section (async logging, DB persist, inline notification), the atomicity evaporates silently.

**We add the lock as defense-in-depth:**
- Correctness survives future changes to the code.
- The overhead is minimal (~0.32 µs for the locked section).
- The structural rule (plain `def` helper, no `await`) makes yielding mechanically impossible.

---

## 5. Edge Cases and Their Handling

### 5.1 Intermittent / Flapping Bridge

**Scenario:** Bridge alternates between up and down repeatedly.

**Behavior:**
- First failure → notification sent, flag set to `True`.
- Subsequent failures (even if bridge recovers and fails again) → no notification.
- `_failure_count` continues climbing.
- `_last_failure_timestamp` updates on each failure.

**Why this is correct:**
- Ongoing flap severity is visible via `_failure_count` and `_last_failure_timestamp` on the status endpoint.
- Re-alerting on each flap is deliberately NOT done (one notification per startup).
- Future extension: recovery-based reset (after N consecutive successes) can re-arm detection so the *next* degradation is a new "first."

### 5.2 Config Change (ADC_TELEGRAM_BRIDGE_URL)

**Scenario:** Environment variable changes at runtime.

**Behavior:**
- `bridge_url` is read once in `__init__` and cached.
- Changing the env var has no effect until restart.
- On restart, the flag resets to `False`, so the new URL's first failure triggers notification.

**Why this is correct:**
- The singleton lifecycle matches the process lifecycle.
- A restart resets both config and detection state, keeping them consistent.
- **Future rule:** Any hot-reload that mutates `bridge_url` on a live instance MUST also call `reset_first_failure_state()`, or the new URL's first failure is suppressed by a stale flag.

### 5.3 4xx vs 5xx vs Transport Errors

**Current behavior (v1):**
- All three failure branches flip the flag identically:
  - Non-2xx HTTP response (including 4xx per-message errors)
  - `httpx.RequestError` (network/transport failures)
  - Any other `Exception`

**Sharp edge:** A single 400 (per-message error) can "use up" the one notification and suppress a later real outage.

**Future enhancement:**
- Scope "first failure" to reachability-class failures only:
  - `httpx.RequestError` (network error, timeout, connection refused)
  - 5xx/429 (bridge-side errors, rate limits)
- Route 4xx to a per-message DEBUG path that does NOT touch the flag.

### 5.4 Recovery-Based Reset (Future)

**Scenario:** Bridge recovers and stays healthy for N consecutive sends.

**Behavior (future):**
- Add `_consecutive_success_count` field.
- In `_handle_send_success`, increment the counter.
- After threshold (e.g., 5 consecutive successes), flip `_has_logged_first_failure` back to `False`.
- Next failure is treated as "first" again.

**Why this is an extension:**
- Out of scope for v1 (per-startup semantic is sufficient).
- Requires adding a success path handler and threshold configuration.
- Prevents "one notification per process" from becoming "one notification ever" for long-running processes.

### 5.5 Notification Failure

**Scenario:** `_notify_first_failure()` raises, times out, or is cancelled.

**Behavior:**
- The flag stays `True` (already set inside the lock before the notify runs).
- Next failure sees `True` and does NOT re-notify.
- The first notification is lost until reset/restart.

**Why this is correct:**
- Desired exactly-once property (no re-notify on subsequent failures).
- If notification retry is needed, it's a notification-layer concern and must NOT un-set the flag.
- Future extension: notification queue with retry logic.

### 5.6 Concurrent First Failures (N Coroutines Race)

**Scenario:** N coroutines all fail at once, all try to acquire the lock.

**Behavior:** (covered in §4)
- Exactly one WARNING log.
- Exactly one `_notify_first_failure()` call.
- All N failures increment `_failure_count`.

**Why this is correct:**
- The lock makes the claim atomic.
- "First" is the winner of the claim, not the earliest timestamp.

---

## 6. Implementation Guidance

### 6.1 Locked Helper (Plain `def`, No `await`)

```python
def _record_failure_locked(self, error_context: str) -> bool:
    """
    Caller MUST hold _first_failure_lock.
    Sync on purpose — no await (prevents yielding mid-check).

    Returns True iff THIS call performed the _has_logged_first_failure
    False→True flip, i.e. this is the first failure of the startup.
    """
    now = datetime.now()

    # Unconditional state updates
    self._is_reachable = False
    self._failure_count += 1
    self._last_failure_timestamp = now

    # THE CHECK: First vs Subsequent
    if not self._has_logged_first_failure:
        # THE CLAIM: Flip the flag
        self._has_logged_first_failure = True
        self._first_failure_timestamp = now

        logger.warning(
            f"First Telegram send failure detected at {self.bridge_url}. "
            f"Error: {error_context or 'unknown error'}. "
            f"Subsequent failures will be logged at DEBUG level only."
        )
        return True  # was_first → triggers notification

    # Subsequent failure path
    logger.debug(
        f"Repeated Telegram send failure #{self._failure_count} "
        f"at {self.bridge_url}. Error: {error_context or 'unknown error'}."
    )
    return False  # not_first → suppress notification
```

### 6.2 Reactive Handler (Acquires Lock, Calls Helper)

```python
async def _handle_send_failure(self, error_context: str = "") -> None:
    """
    Reactive detection entry point.
    Called only from send_message failure branches.
    """
    was_first = False

    # Serialize the critical section
    async with self._first_failure_lock:
        was_first = self._record_failure_locked(error_context)

    # Lock released; notification runs outside
    if was_first:
        await self._notify_first_failure(error_context)
```

### 6.3 Call Sites in `send_message`

```python
# Inside send_message — three failure branches, all now awaited:
#   non-2xx  → await self._handle_send_failure(error_msg)
#   RequestError → await self._handle_send_failure(error_msg)
#   other Exception → await self._handle_send_failure(error_msg)
```

### 6.4 Side-Channel Notification (No Recursive Send)

```python
async def _notify_first_failure(self, error_context: str) -> None:
    """
    Deliver the once-per-startup alert over a SIDE CHANNEL.

    MUST NOT call self.send_message(...): the bridge just failed for the
    same reason, and a failure here would pollute _failure_count /
    _last_failure_timestamp with self-failures.
    """
    # TODO(notification bead): choose the side channel.
    # Options: stderr, structured log sink, separate transport.
    return
```

---

## 7. Verification

### 7.1 Unit Tests

- **Single first failure:** Call `_handle_send_failure` once → `_has_logged_first_failure == True`, WARNING logged, `_notify_first_failure` called.
- **Subsequent suppression:** Call twice → second call sees `True`, logs DEBUG only, no `_notify_first_failure`.
- **Concurrent failures:** `asyncio.gather(*[_handle_send_failure() for _ in range(10)])` → exactly one WARNING, `_failure_count == 10`, one `_first_failure_timestamp`.
- **Counter accuracy:** 100 concurrent calls → `_failure_count == 100`.
- **Reset re-arms:** `reset_first_failure_state()` → flag back to `False`, next failure is "first" again.
- **Flag not reset on restart:** New `TelegramFallback()` instance → flag starts as `False`.

### 7.2 Structural Tests

- **No I/O in locked section:** `assert inspect.iscoroutinefunction(_record_failure_locked) is False`.
- **Notification outside lock:** `_notify_first_failure` is called AFTER the `async with` block exits.

---

## 8. Acceptance Criteria Mapping

| Criterion | Where Addressed |
|-----------|-----------------|
| Detection logic documented with clear pseudo-code or flow | §2 (check algorithm), §6 (implementation guidance) |
| Explains how "first" is determined | §2 (claim-and-set pattern) |
| Explains why subsequent failures are ignored | §3 (boolean flag latch, no reset window) |
| Depends on child bead adc-50ld completing thread-safety design | Thread-safety from adc-50ld integrated (lock pattern, await-free helper) |

---

## 9. References

- **Comprehensive design:** `notes/adc-14la-first-failure-tracking-design.md` — end-to-end flow, state model, concurrency analysis
- **Thread-safety:** `notes/adc-50ld-thread-safety-approach.md` — lock pattern, latent-vs-active race, performance
- **Data structure:** `notes/adc-65l3-first-failure-state-structure.md` — field definitions, reset semantics
- **Storage:** `notes/adc-2duz-state-storage-design.md` — flat instance vars, in-memory per-startup
- **Current code:** `src/telegram/fallback.py` — `_handle_send_failure`, `send_message`
