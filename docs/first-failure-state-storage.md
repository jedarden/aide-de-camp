# First-Failure State Storage Design for Async FastAPI

## Overview

This document designs **WHERE** the first-failure state lives in the async FastAPI application (aide-de-camp), building on the data structure design from adc-65l3 and the tracking mechanism design from adc-4vhr.

## Storage Options Evaluation

### Option 1: Module-Level Variable ❌

```python
# src/telegram/fallback.py
_first_failure_state = FirstFailureState()

def get_first_failure_state():
    return _first_failure_state
```

**Pros:**
- Simple, familiar pattern (used in `ambient.py` for `_ambient_monitor`)
- Easy to access from anywhere in the module
- Clear singleton semantics

**Cons:**
- **Thread-safety**: Harder to protect with locks in async context
- **Testing**: Difficult to reset or mock in tests
- **Encapsulation**: Global state is harder to reason about
- **Dependency injection**: Impossible to inject alternative implementations

**Verdict**: ❌ Not recommended for state that requires atomic transitions

---

### Option 2: Class Attribute (Instance Variable) ✅ RECOMMENDED

```python
# src/telegram/fallback.py
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        self.bridge_url = bridge_url or os.getenv("ADC_TELEGRAM_BRIDGE_URL", "http://telegram-claude-bridge:8000")
        self._first_failure_state = FirstFailureState()
        self._state_lock = asyncio.Lock()  # Protects state transitions
```

**Pros:**
- **Encapsulation**: State is scoped to the instance
- **Thread-safety**: Can protect with instance-level locks
- **Testing**: Easy to reset or mock via class instantiation
- **Singleton pattern**: `get_telegram_fallback()` ensures single instance
- **Dependency injection**: Can inject mock tracker in tests
- **Consistency**: Matches existing `_ambient_monitor` pattern

**Cons:**
- Slightly more complex than module-level
- Requires careful lock management

**Verdict**: ✅ **RECOMMENDED** - Best balance of simplicity, testability, and thread-safety

---

### Option 3: Request Context (via FastAPI `contextvar`) ❌

```python
from fastapi import Request
_first_failure_state = ContextVar("first_failure_state")

@app.post("/send")
async def send_message(request: Request):
    state = _first_failure_state.get(None)
    # ...
```

**Pros:**
- Request-scoped state
- No shared state between requests

**Cons:**
- **Wrong semantics**: First-failure state is APPLICATION-scoped, not request-scoped
- **No persistence**: Lost after each request
- **Cannot track**: Cannot track "first failure after startup" across requests

**Verdict**: ❌ Not applicable - wrong scoping model

---

### Option 4: Database (SQLite/PostgreSQL) ❌

```python
async def record_failure(error_context: str):
    async with aiosqlite.connect("first_failures.db") as db:
        await db.execute(
            "INSERT INTO first_failures (startup_time, error_context) VALUES (?, ?)",
            (startup_time, error_context)
        )
```

**Pros:**
- Persistent across restarts
- Queryable for metrics
- Can build historical analytics

**Cons:**
- **Overkill**: Too complex for simple in-memory state tracking
- **I/O overhead**: Database writes on every failure
- **Contention**: Database locks can become bottleneck
- **Complexity**: Need schema management, migrations, cleanup

**Verdict**: ❌ Not recommended as primary storage (use as optional persistence layer only)

---

## Recommended Design: Class Attribute with Lock

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   TelegramFallback                          │
│                   (singleton via get_*)                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  _first_failure_state: FirstFailureState            │  │
│  │  - has_failed: bool = False                           │  │
│  │  - first_failure_at: Optional[datetime] = None         │  │
│  │  - channel_id: Optional[str] = None                    │  │
│  │  - error_type: Optional[str] = None                   │  │
│  │  - error_message: Optional[str] = None                │  │
│  │  - total_failures: int = 0                            │  │
│  │  - notification_sent: bool = False                    │  │
│  │  - notification_sent_at: Optional[datetime] = None     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  _state_lock: asyncio.Lock                            │  │
│  │  (protects all _first_failure_state mutations)        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Pattern

```python
# src/telegram/fallback.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

@dataclass
class FirstFailureState:
    """Tracks the first Telegram send failure after startup.
    
    This state is used to detect and report only the FIRST failure,
    preventing notification spam on subsequent send failures.
    """
    has_failed: bool = False
    first_failure_at: Optional[datetime] = None
    channel_id: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    total_failures: int = 0
    notification_sent: bool = False
    notification_sent_at: Optional[datetime] = None

class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        import os
        self.bridge_url = bridge_url or os.getenv(
            "ADC_TELEGRAM_BRIDGE_URL", "http://telegram-claude-bridge:8000"
        )
        # State storage: class attribute (instance variable)
        self._first_failure_state = FirstFailureState()
        # Thread-safety: asyncio.Lock protects state mutations
        self._state_lock = asyncio.Lock()
        # Optional: persistence layer (env-var controlled)
        self._persistence_enabled = os.getenv("ADC_FIRST_FAILURE_DB") is not None

    async def _record_first_failure(
        self,
        channel_id: str,
        error: Exception,
    ) -> FirstFailureState:
        """Record the first failure with thread-safety guarantees.
        
        This method is atomic: concurrent calls will serialize and only
        the first call will record the first-failure state.
        """
        async with self._state_lock:
            # Double-check pattern: lock ensures only one thread sees False
            if not self._first_failure_state.has_failed:
                # First failure! Record all details
                self._first_failure_state.has_failed = True
                self._first_failure_state.first_failure_at = datetime.now(timezone.utc)
                self._first_failure_state.channel_id = channel_id
                self._first_failure_state.error_type = type(error).__name__
                self._first_failure_state.error_message = str(error)[:500]  # Truncate
                self._first_failure_state.total_failures += 1
                
                # Optional: persist to database if enabled
                if self._persistence_enabled:
                    await self._persist_first_failure()
                
                logger.warning(
                    f"First Telegram send failure detected: "
                    f"{self._first_failure_state.error_type}: "
                    f"{self._first_failure_state.error_message}"
                )
            else:
                # Subsequent failure - just increment counter
                self._first_failure_state.total_failures += 1
                logger.debug(
                    f"Subsequent Telegram send failure "
                    f"(total: {self._first_failure_state.total_failures})"
                )
        
        return self._first_failure_state

    async def _persist_first_failure(self) -> None:
        """Persist first-failure event to database (optional)."""
        import os
        db_path = os.getenv("ADC_FIRST_FAILURE_DB")
        if not db_path:
            return
        
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """INSERT INTO first_failures 
                   (startup_time, first_failure_time, channel_id, error_type, error_message)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),  # Approximate startup time
                    self._first_failure_state.first_failure_at.isoformat(),
                    self._first_failure_state.channel_id,
                    self._first_failure_state.error_type,
                    self._first_failure_state.error_message,
                )
            )
            await db.commit()

    def get_first_failure_state(self) -> FirstFailureState:
        """Get current first-failure state (read-only, for testing/monitoring)."""
        return self._first_failure_state

# Global singleton instance (matches existing pattern)
_telegram_fallback: Optional[TelegramFallback] = None

def get_telegram_fallback() -> TelegramFallback:
    """Get or create the global Telegram fallback instance."""
    global _telegram_fallback
    if _telegram_fallback is None:
        _telegram_fallback = TelegramFallback()
    return _telegram_fallback
```

---

## Lifecycle Management

### Initialization Timing

**When does the state initialize?**

```python
# Lazy initialization - on first use
_telegram_fallback = None  # Module load time

def get_telegram_fallback() -> TelegramFallback:
    global _telegram_fallback
    if _telegram_fallback is None:
        # State initializes HERE - on first call after startup
        _telegram_fallback = TelegramFallback()
    return _telegram_fallback
```

**Timeline:**
1. Application startup → uvicorn loads `src.telegram.fallback` module
2. Module globals initialized (`_telegram_fallback = None`)
3. FastAPI app starts serving requests
4. First request calls `get_telegram_fallback()`
5. **State initialized**: `_first_failure_state = FirstFailureState()` with default values

**Why lazy initialization?**
- Faster startup (no unnecessary I/O or DB connections)
- Only initialize when actually needed
- Consistent with existing `get_ambient_monitor()` pattern

**Alternative: Eager initialization**
```python
# At module load time
_telegram_fallback = TelegramFallback()  # Initializes immediately

def get_telegram_fallback() -> TelegramFallback:
    return _telegram_fallback
```
- Also valid, but slower startup
- Use if you want to fail-fast on initialization errors

---

### Reset Behavior

#### 1. Application Startup (Automatic Reset) ✅

```python
# Process restart → fresh state
$ uvicorn src.main:app --reload
# New process → _telegram_fallback = None → new FirstFailureState()
```

**Behavior:**
- All fields reset to defaults: `has_failed=False`, `total_failures=0`, etc.
- This is **desired behavior**: first-failure tracking is per-process
- No manual reset needed after restart

**When this happens:**
- Server restart (`systemctl restart aide-de-camp`)
- Deployment rollback
- Crash and restart
- Development: code change with `--reload`

---

#### 2. Manual Reset (Admin Action) 🛠️

**Scenario**: Admin manually resolved a Telegram issue and wants to reset failure tracking.

**Option A: Application Restart (Simplest)**
```bash
# Just restart the app
systemctl restart aide-de-camp
# State resets automatically
```

**Option B: Runtime Reset (via API endpoint)**
```python
# Add admin endpoint to FastAPI app
@app.post("/admin/reset-first-failure-state")
async def reset_first_failure_state():
    """Reset first-failure tracking (admin only)."""
    telegram = get_telegram_fallback()
    async with telegram._state_lock:
        telegram._first_failure_state = FirstFailureState()
    return {"status": "reset", "message": "First-failure state cleared"}
```

**Option C: Selective Reset (Partial)**
```python
# Reset only specific fields
async def reset_first_failure_tracking():
    telegram = get_telegram_fallback()
    async with telegram._state_lock:
        telegram._first_failure_state.has_failed = False
        telegram._first_failure_state.first_failure_at = None
        telegram._first_failure_state.notification_sent = False
        # Keep total_failures for historical context
```

**Recommendation**: Use application restart for production (simplest, no added complexity). Runtime reset only needed for long-running processes where restart is expensive.

---

#### 3. No Auto-Reset After Notification ⚠️

**IMPORTANT**: The state does **NOT** automatically reset after sending the first-failure notification.

```python
# ❌ WRONG - auto-reset after notification (DO NOT DO THIS)
if not self._first_failure_state.has_failed:
    await send_first_failure_notification(...)
    self._first_failure_state = FirstFailureState()  # <-- WRONG!

# ✅ CORRECT - state persists after notification
if not self._first_failure_state.has_failed:
    await send_first_failure_notification(...)
    # State persists - subsequent failures see has_failed=True
```

**Why no auto-reset?**
- Prevents notification spam if failures continue
- Single "first failure after startup" event per process lifetime
- Diagnostic value: state remains queryable for debugging

---

## Persistence Requirements

### Question: Does the state survive restarts?

**Answer: No (by design).**

### Rationale: Why Not Persist?

**1. Per-Process Semantics**
- "First failure after startup" is inherently process-scoped
- Each restart is a new startup event
- Persisting would conflate "first after THIS startup" with "first EVER"

**2. Diagnostic Clarity**
- If state persisted, couldn't distinguish "never failed" from "failed before last restart"
- Current semantics: `has_failed=False` means "clean since this startup"

**3. Simplicity**
- No database schema needed
- No migration/cleanup complexity
- Faster startup (no DB reads)

**4. Failure Detection Use Case**
- Purpose: Alert on NEW failures after restart
- If failures persist across restarts, that's a separate problem (service outage)
- Persistent failures should be detected by monitoring (Prometheus, etc.)

---

### Optional Persistence Layer (Enhancement)

**Purpose**: Historical tracking, not runtime state management.

```python
# Environment variable controls persistence
$ export ADC_FIRST_FAILURE_DB=/tmp/first_failures.db
```

**Schema**:
```sql
CREATE TABLE first_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    startup_time TEXT NOT NULL,
    first_failure_time TEXT NOT NULL,
    channel_id TEXT,
    error_type TEXT,
    error_message TEXT,
    resolved INTEGER DEFAULT 0
);
```

**Usage**:
```python
# In _record_first_failure():
if self._persistence_enabled:
    await self._persist_first_failure()  # Write to DB
```

**Queries**:
```python
# Get first-failure history for last 7 days
async def get_first_failure_history(days: int = 7):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """SELECT * FROM first_failures 
               WHERE first_failure_time > datetime('now', ?) 
               ORDER BY first_failure_time DESC""",
            (f"-{days} days",)
        )
        return await cursor.fetchall()
```

**Benefits**:
- Post-mortem analysis: "When did the first failure occur?"
- Metrics: "How many startups had first failures?"
- Debugging: Correlate first failures with deployments

**Trade-offs**:
- Optional: only enabled in production via env var
- Separate from in-memory state (for runtime decisions)
- Queryable via API endpoint for monitoring

---

## Thread-Safety Strategy

### Why asyncio.Lock?

**Problem**: FastAPI handles concurrent requests asynchronously. Multiple coroutines can call `_record_first_failure()` simultaneously.

**Race Condition Without Lock**:
```python
# Thread 1                    # Thread 2
if not state.has_failed:     if not state.has_failed:
                              # Both see False!
state.has_failed = True      
log WARNING()                state.has_failed = True
                              log WARNING()  # DUPLICATE!
```

**Solution**: asyncio.Lock ensures atomic check-and-set.

```python
async with self._state_lock:
    if not self._first_failure_state.has_failed:
        # Only one thread can execute this block at a time
        self._first_failure_state.has_failed = True
        # ... record details ...
```

**Lock Acquisition Pattern**:
- Lock protects ONLY state mutations
- Held for microseconds (negligible overhead)
- No I/O inside lock (persistence is outside or optional)
- Compatible with async/await throughout

**Performance Impact**:
- Lock contention is minimal (failures are rare)
- Overhead: ~10-100 microseconds per acquisition
- Compare to HTTP I/O: 10+ seconds (100,000x slower than lock)

---

## Testing Strategy

### Unit Tests (State Transitions)

```python
import pytest
from datetime import datetime, timezone

@pytest.mark.asyncio
async def test_first_failure_recording():
    """Verify first failure is recorded correctly."""
    telegram = TelegramFallback()
    
    # Initially: no failures
    assert telegram._first_failure_state.has_failed is False
    assert telegram._first_failure_state.total_failures == 0
    
    # Record first failure
    state = await telegram._record_first_failure(
        channel_id="@test",
        error=Exception("Test error")
    )
    
    # Verify state updated
    assert state.has_failed is True
    assert state.total_failures == 1
    assert state.error_type == "Exception"
    assert state.error_message == "Test error"
    assert state.first_failure_at is not None
    assert isinstance(state.first_failure_at, datetime)

@pytest.mark.asyncio
async def test_concurrent_first_failures():
    """Verify only one first failure when multiple failures happen concurrently."""
    telegram = TelegramFallback()
    
    # Simulate 10 concurrent failures
    import asyncio
    tasks = [
        telegram._record_first_failure("@test", Exception(f"Error {i}"))
        for i in range(10)
    ]
    results = await asyncio.gather(*tasks)
    
    # All should return the same first-failure state
    for result in results:
        assert result.has_failed is True
        assert result.total_failures == 10  # All 10 counted
    
    # But first_failure_at should be from the FIRST one only
    first_timestamp = results[0].first_failure_at
    assert all(r.first_failure_at == first_timestamp for r in results)
```

### Integration Tests (Logging Behavior)

```python
import pytest
import logging

@pytest.mark.asyncio
async def test_first_failure_logging(caplog):
    """Verify WARNING on first failure, DEBUG on subsequent."""
    telegram = TelegramFallback()
    
    # First failure: WARNING
    with caplog.at_level(logging.WARNING):
        await telegram._record_first_failure("@test", Exception("Error 1"))
    assert "First Telegram send failure detected" in caplog.text
    
    # Second failure: DEBUG only
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        await telegram._record_first_failure("@test", Exception("Error 2"))
    assert "Subsequent Telegram send failure" in caplog.text
    assert "First Telegram send failure" not in caplog.text
```

### Reset Tests

```python
@pytest.mark.asyncio
async def test_manual_reset():
    """Verify manual reset clears state correctly."""
    telegram = TelegramFallback()
    
    # Record a failure
    await telegram._record_first_failure("@test", Exception("Error"))
    assert telegram._first_failure_state.has_failed is True
    
    # Reset state
    async with telegram._state_lock:
        telegram._first_failure_state = FirstFailureState()
    
    # Verify cleared
    assert telegram._first_failure_state.has_failed is False
    assert telegram._first_failure_state.total_failures == 0
```

---

## Summary

### Storage Location: Class Attribute (Instance Variable)

**Location**: `TelegramFallback._first_failure_state`

**Rationale**:
- ✅ Thread-safe with `asyncio.Lock`
- ✅ Easy to test (instantiate, reset, mock)
- ✅ Singleton pattern via `get_telegram_fallback()`
- ✅ Consistent with existing patterns (`_ambient_monitor`)
- ✅ Encapsulated (not global state)

### Initialization: Lazy (on First Use)

**Timing**: When `get_telegram_fallback()` is first called

**Why**:
- Faster startup
- Only initialize when needed
- Fail-fast on initialization errors (when first used)

### Reset Behavior

1. **Automatic reset on startup**: All fields reset to defaults (desired)
2. **Manual reset**: Via application restart or admin endpoint
3. **No auto-reset after notification**: State persists to prevent spam

### Persistence: In-Memory (No Restart Survival)

**Rationale**:
- "First failure after startup" is inherently process-scoped
- Clear semantics: `has_failed=False` = clean since this startup
- Simplicity: no DB schema, migrations, or cleanup
- Optional persistence via env var for historical tracking (not runtime state)

### Thread-Safety: asyncio.Lock

**Why**:
- Atomic check-and-set operations
- Minimal overhead (microseconds)
- Compatible with async/await
- Prevents duplicate first-failure notifications

---

## References

- **Data structure design**: `docs/first-failure-state-structure.md` (adc-65l3)
- **Tracking mechanism design**: `notes/adc-4vhr.md`
- **Current implementation**: `src/telegram/fallback.py`
- **Ambient monitoring pattern**: `src/monitoring/ambient.py` (similar singleton pattern)

---

**Document**: adc-2duz  
**Status**: ✅ Design Complete  
**Dependencies**: adc-65l3 (data structure), adc-4vhr (tracking mechanism)  
**Date**: 2026-07-02
