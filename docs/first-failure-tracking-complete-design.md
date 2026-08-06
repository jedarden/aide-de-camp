# First-Failure Tracking — Complete Design Document

**Bead:** adc-14la — "Document complete first-failure tracking design"
**Child of:** adc-4vhr (Design first-failure tracking mechanism)
**Status:** Design Complete
**Date:** 2026-08-06
**Dependencies:** adc-65l3 (data structure), adc-2duz (storage), adc-50ld (thread-safety), adc-12bt (detection logic)

---

## Executive Summary

This document synthesizes the complete first-failure tracking design for aide-de-camp's Telegram integration. The design ensures **exactly one WARNING-level notification is emitted per process startup** when the Telegram bridge becomes unreachable, while all subsequent failures are logged at DEBUG level only.

**Key Design Decisions:**
- **Storage:** Instance variables on `TelegramFallback` singleton (in-memory, per-startup)
- **Thread-Safety:** Single `asyncio.Lock` protecting state mutations
- **Detection Logic:** Reactive check after actual send failure (no pre-send probe)
- **Persistence:** None by design (state resets on application restart)

**Core Invariant:** One notification per startup. No notification spam during prolonged outages.

---

## 1. Component Integration Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     First-Failure Tracking System                    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  1. DATA STRUCTURE (adc-65l3)                                │  │
│  │  ───────────────────────────────────────────────────────────  │  │
│  │  Location: Instance variables on TelegramFallback           │  │
│  │                                                                 │  │
│  │  Fields:                                                       │  │
│  │  • _has_logged_first_failure: bool = False                   │  │
│  │  • _failure_count: int = 0                                    │  │
│  │  • _first_failure_timestamp: Optional[datetime] = None       │  │
│  │  • _last_failure_timestamp: Optional[datetime] = None         │  │
│  │  • _first_failure_lock: asyncio.Lock                         │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                     │                                │
│                                     ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  2. STORAGE MECHANISM (adc-2duz)                             │  │
│  │  ───────────────────────────────────────────────────────────  │  │
│  │  Location: TelegramFallback._first_failure_state             │  │
│  │  Lifecycle: Lazy init on first get_telegram_fallback() call  │  │
│  │  Persistence: None (in-memory, resets on restart)            │  │
│  │  Access: get_bridge_status() for read-only queries           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                     │                                │
│                                     ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  3. THREAD-SAFETY (adc-50ld)                                 │  │
│  │  ───────────────────────────────────────────────────────────  │  │
│  │  Mechanism: asyncio.Lock on instance                        │  │
│  │  Scope: Protects all _first_failure_state mutations         │  │
│  │  Pattern: await-free _record_failure_locked() helper       │  │
│  │  Performance: ~0.32 µs overhead (uncontended)                │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                     │                                │
│                                     ▼                                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  4. DETECTION LOGIC (adc-12bt)                              │  │
│  │  ───────────────────────────────────────────────────────────  │  │
│  │  Timing: Reactive (after actual send failure)               │  │
│  │  Predicate: has_logged_first_failure False→True transition  │  │
│  │  Semantics: Claim-and-set (atomic check-then-act)           │  │
│  │  Concurrency: Lock ensures exactly one winner among N        │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. End-to-End Flow Description

### 2.1 Lifecycle Timeline

```
APPLICATION STARTUP
    │
    ├─► FastAPI lifespan starts (src/main.py:150-162)
    │   └─► get_telegram_fallback() called
    │       └─► TelegramFallback() initialized
    │           └─► _first_failure_state fields set to defaults:
    │               • _has_logged_first_failure = False
    │               • _failure_count = 0
    │               • _first_failure_timestamp = None
    │               • _last_failure_timestamp = None
    │               • _first_failure_lock = asyncio.Lock()
    │
    ├─► Bridge health check (startup probe, separate channel)
    │   └─► check_bridge_available() called once
    │   └─► Sets _is_reachable (NOT first-failure state)
    │
    ├─► Application serves requests normally
    │
    ├─► FIRST SEND FAILURE OCCURS
    │   │
    │   ├─► send_message() fails (non-2xx / RequestError / Exception)
    │   │   └─► _handle_send_failure(error_context) called
    │   │       │
    │   │       ├─► async with _first_failure_lock:
    │   │       │   └─► _record_failure_locked(error_context)
    │   │       │       │
    │   │       │       ├─► _failure_count += 1
    │   │       │       ├─► _last_failure_timestamp = now
    │   │       │       ├─► _is_reachable = False
    │   │       │       │
    │   │       │       ├─► if not _has_logged_first_failure:
    │   │       │       │   ├─► _has_logged_first_failure = True  ◄── CLAIM
    │   │       │       │   ├─► _first_failure_timestamp = now
    │   │       │       │   ├─► logger.warning("First Telegram send failure...")
    │   │       │       │   └─► return was_first = True
    │   │       │       │
    │   │       │       └─► return was_first = False
    │   │       │
    │   │       └─► Lock released
    │   │           │
    │   │           ├─► if was_first:
    │   │           │   └─► await _notify_first_failure(error_context)
    │   │           │       └─► Side-channel notification (NOT send_message)
    │   │           │
    │   │           └─► else:
    │   │               └─► logger.debug("Repeated Telegram send failure...")
    │   │
    │   └─► NOTIFICATION SENT (exactly once)
    │       └─► Operator receives alert
    │
    ├─► SUBSEQUENT FAILURES (second, third, ... Nth)
    │   │
    │   └─► send_message() fails again
    │       └─► _handle_send_failure(error_context) called
    │           ├─► async with _first_failure_lock:
    │           │   └─► _record_failure_locked(error_context)
    │           │       ├─► _failure_count += 1
    │           │       ├─► _last_failure_timestamp = now
    │           │       ├─► if not _has_logged_first_failure:  # Now True!
    │           │       │   └─► Skipped
    │           │       └─► return was_first = False
    │           └─► logger.debug("Repeated Telegram send failure #N...")
    │
    ├─► ONGOING OUTAGE (fails continue)
    │   ├─► _failure_count increments each time
    │   ├─► _last_failure_timestamp updates each time
    │   ├─► NO MORE WARNINGs (only DEBUG)
    │   └─► Operator can check status endpoint for current state
    │
    ├─► APPLICATION RESTART
    │   ├─► Process exit → Singleton destroyed
    │   └─► New process → Fresh state → Next failure will be "first" again
    │
    └─► MANUAL RESET (future feature)
        └─► reset_first_failure_state() under lock
            └─► _has_logged_first_failure = False
            └─► Next failure becomes "first" again
```

---

## 3. Component Specifications Summary

### 3.1 Data Structure (adc-65l3)

State fields on `TelegramFallback`:
- `_has_logged_first_failure: bool = False` — Primary flag
- `_failure_count: int = 0` — Total failures since startup
- `_first_failure_timestamp: Optional[datetime] = None` — Timestamp of first failure
- `_last_failure_timestamp: Optional[datetime] = None` — Timestamp of most recent failure
- `_first_failure_lock: asyncio.Lock` — Protects mutations

### 3.2 Storage (adc-2duz)

**Decision:** Instance variables on `TelegramFallback` singleton.
**Lifecycle:** Lazy init, in-memory, per-startup (resets on restart).
**Access:** `get_bridge_status()` for read-only queries.

### 3.3 Thread-Safety (adc-50ld)

**Mechanism:** Single `asyncio.Lock` guarding await-free critical section.
**Protected:** All `_first_failure_state` mutations.
**Performance:** ~0.32 µs overhead (uncontended).
**Prevents:** Duplicate WARNINGs, lost counter updates, timestamp overwrites.

### 3.4 Detection Logic (adc-12bt)

**Predicate:** Failure is "first" iff it performs `_has_logged_first_failure` False→True transition under lock.
**Timing:** Reactive only (after actual send failure).
**Concurrency:** Lock ensures exactly one winner among N concurrent failures.
**Why subsequent ignored:** Core invariant "notify once"; flag is monotonic; diagnostics preserved via counters/timestamps.

---

## 4. Implementation Guidance

### 4.1 Key Code Pattern

```python
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # First-failure tracking state
        self._has_logged_first_failure: bool = False
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None
        self._last_failure_timestamp: Optional[datetime] = None
        self._first_failure_lock: asyncio.Lock = asyncio.Lock()

    async def _handle_send_failure(self, error_context: str = "") -> None:
        was_first = False
        async with self._first_failure_lock:
            was_first = self._record_failure_locked(error_context)
        
        if was_first:
            await self._notify_first_failure(error_context)
        else:
            logger.debug(f"Repeated Telegram send failure #{self._failure_count}...")

    def _record_failure_locked(self, error_context: str) -> bool:
        """Caller MUST hold _first_failure_lock. Sync on purpose — no await."""
        now = datetime.now()
        self._is_reachable = False
        self._failure_count += 1
        self._last_failure_timestamp = now

        if not self._has_logged_first_failure:
            self._has_logged_first_failure = True
            self._first_failure_timestamp = now
            logger.warning(f"First Telegram send failure detected...")
            return True
        return False

    async def _notify_first_failure(self, error_context: str) -> None:
        """Side-channel notification (NOT send_message)."""
        # TODO: Implement via stderr / structured log / different transport
        pass
```

### 4.2 Testing Requirements

**Unit Tests:**
- State transitions (first failure sets flag/timestamps)
- Counter increments on subsequent failures
- Manual reset clears state correctly

**Integration Tests:**
- WARNING on first, DEBUG on subsequent
- No duplicate WARNINGs under concurrency

**Thread-Safety Tests:**
- 100 concurrent failures → count == 100
- Exactly one WARNING under concurrent first failures

**Edge Cases:**
- Intermittent failures → single notification
- Notification failure → flag stays True
- Reset vs in-flight failure → serialize cleanly

### 4.3 Migration from Current Code

**Changes to `src/telegram/fallback.py`:**
1. Rename `_last_failure_logged` → `_last_failure_timestamp`
2. Add `_first_failure_timestamp: Optional[datetime] = None`
3. Add `_first_failure_lock: asyncio.Lock = asyncio.Lock()`
4. Refactor `_handle_send_failure` to use lock + helper pattern
5. Update `_last_failure_timestamp` on every failure

---

## 5. Acceptance Criteria — Mapping

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Complete design documented | ✅ | Sections 1-4 provide complete specification |
| All components integrated coherently | ✅ | Section 1 shows component relationships; Section 2 shows end-to-end flow |
| Clear implementation guidance | ✅ | Section 4 provides code structure, tests, migration steps |
| Depends on adc-12bt | ✅ | adc-12bt closed 2026-08-06; design consumes its detection logic |

---

## 6. References to Child Artifacts

- **adc-65l3:** `notes/adc-65l3-first-failure-state-structure.md` — Data structure definition
- **adc-2duz:** `docs/first-failure-state-storage.md` — Storage mechanism design
- **adc-50ld:** `notes/adc-50ld-thread-safety-approach.md` — Locking strategy
- **adc-12bt:** `notes/adc-12bt-first-failure-detection-logic.md` — Detection predicate
- **adc-5xuy:** `notes/adc-5xuy-thread-safety-design.md` — Comprehensive thread-safety spec
- **adc-4ol5:** `docs/race-conditions-first-failure-state.md` — Race condition catalog

---

## 7. Next Steps

The implementation bead should:
1. Add state structure fields to `TelegramFallback.__init__`
2. Refactor `_handle_send_failure` to use lock + `_record_failure_locked` pattern
3. Implement `_notify_first_failure` side-channel notification
4. Add comprehensive test suite
5. Update `get_bridge_status()` to expose new fields
6. Document migration from current code

**Readiness:** ✅ All child beads closed; design complete and internally consistent. Ready for implementation.

---

**Document:** adc-14la  
**Status:** ✅ Design Complete  
**Total Design Artifacts:** 4 child beads + 1 synthesis = 5  
**Next Phase:** Implementation (TBD)
