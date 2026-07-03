# First-Failure State Storage Design

## Overview

This document evaluates storage options for the first-failure tracking state in the async FastAPI application and documents the recommended approach with rationale.

## Design Requirements

### Functional Requirements
1. State must track first-failure occurrence across application lifetime
2. State must survive from application startup until shutdown
3. Only ONE first-failure event should be detected per startup sequence
4. State must be accessible to all `send_message()` calls

### Non-Functional Requirements
1. **Thread-safety**: Multiple concurrent async requests must not corrupt state
2. **Performance**: Minimal overhead on the hot path (Telegram sends)
3. **Lifecycle clarity**: Clear initialization and reset behavior
4. **Simplicity**: Easy to understand, test, and maintain

## Storage Options Evaluation

### Option 1: Module-Level Variable

**Approach:**
```python
# In src/telegram/fallback.py
_first_failure_state = {
    "has_logged_first_failure": False,
    "failure_count": 0,
    "first_failure_timestamp": None,
    "last_failure_timestamp": None,
}
```

**Pros:**
- Simple to understand
- Accessible from anywhere in the module
- No instance overhead

**Cons:**
- ❌ **Not thread-safe**: Concurrent async coroutines can race on check-and-set
- ❌ **Hard to test**: Global state pollutes tests; requires manual reset
- ❌ **No encapsulation**: Any code can mutate state directly
- ❌ **No lock integration**: Would need a separate global lock object

**Verdict:** ❌ **REJECTED** - Not thread-safe in async context

---

### Option 2: Class Attribute (Shared State)

**Approach:**
```python
class TelegramFallback:
    # Class attribute - shared across ALL instances
    _has_logged_first_failure: bool = False
    _first_failure_lock: asyncio.Lock = None
    
    @classmethod
    async def get_class_lock(cls):
        if cls._first_failure_lock is None:
            cls._first_failure_lock = asyncio.Lock()
        return cls._first_failure_lock
```

**Pros:**
- State shared across all instances (if multiple were created)
- Class-level organization

**Cons:**
- ❌ **Unnecessary complexity**: `TelegramFallback` is a singleton anyway
- ❌ **Lock initialization timing**: Class attrs init at import time, before event loop
- ❌ **Testing complexity**: Hard to reset between tests
- ❌ **Surprising behavior**: Shared state across instances is non-obvious

**Verdict:** ❌ **REJECTED** - Adds complexity without benefit

---

### Option 3: Instance Variable (Per-Instance State)

**Approach:**
```python
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # Instance variables
        self._has_logged_first_failure = False
        self._failure_count = 0
        self._first_failure_timestamp = None
        self._last_failure_timestamp = None
        self._first_failure_lock = asyncio.Lock()
```

**Pros:**
- ✅ **Thread-safe with lock**: `asyncio.Lock` serializes concurrent access
- ✅ **Clear lifecycle**: Initializes when instance creates, dies when instance destroyed
- ✅ **Singleton pattern**: `get_telegram_fallback()` ensures one instance per app
- ✅ **Encapsulated**: State lives inside the class that uses it
- ✅ **Testable**: Each test can create a fresh instance
- ✅ **Natural reset**: Application restart = new instance = reset state

**Cons:**
- None significant for this use case

**Verdict:** ✅ **RECOMMENDED** - Matches all requirements

---

### Option 4: Request Context (Per-Request State)

**Approach:**
```python
from starlette.requests import Request

async def send_message(request: Request, chat_id, message):
    # Store in request.state
    if not hasattr(request.state, "first_failure_logged"):
        request.state.first_failure_logged = True
        logger.warning("First failure...")
```

**Pros:**
- Natural isolation per request

**Cons:**
- ❌ **Wrong lifecycle**: Request-scoped means state resets EVERY request
- ❌ **Violates requirement**: Need ONE first-failure per startup, not per request
- ❌ **Impossible**: Would need to persist across requests (defeats the purpose)

**Verdict:** ❌ **REJECTED** - Wrong lifecycle for this requirement

---

### Option 5: Database Persistence

**Approach:**
```python
# Store in SQLite or PostgreSQL
CREATE TABLE first_failure_state (
    id SERIAL PRIMARY KEY,
    has_logged_first_failure BOOLEAN DEFAULT FALSE,
    failure_count INTEGER DEFAULT 0,
    first_failure_timestamp TIMESTAMP,
    last_failure_timestamp TIMESTAMP
);
```

**Pros:**
- Survives application restarts
- Queryable for monitoring

**Cons:**
- ❌ **Wrong lifecycle**: First-failure should RESET on restart, not persist
- ❌ **Performance overhead**: Database write on every failure (hot path)
- ❌ **Overkill**: No need for persistence; state is transient by design
- ❌ **Complexity**: Adds database dependency for simple boolean flag

**Verdict:** ❌ **REJECTED** - Adds complexity for wrong lifecycle

---

## Recommended Design: Instance Variable with Singleton

### Storage Location

**Primary storage:** Instance variables in `TelegramFallback` class

```python
# src/telegram/fallback.py
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # ... existing initialization ...
        
        # First-failure tracking state (instance variables)
        self._has_logged_first_failure: bool = False
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None
        self._last_failure_timestamp: Optional[datetime] = None
        
        # Thread-safety: async lock for concurrent access
        self._first_failure_lock: asyncio.Lock = asyncio.Lock()
```

### Global Access via Singleton

The application uses a module-level singleton pattern:

```python
# Global instance (module-level)
_telegram_fallback: Optional[TelegramFallback] = None

def get_telegram_fallback() -> TelegramFallback:
    """Get or create the global Telegram fallback instance."""
    global _telegram_fallback
    if _telegram_fallback is None:
        _telegram_fallback = TelegramFallback()
    return _telegram_fallback
```

**Why this works:**
1. **First call**: Creates the singleton instance, initializes state
2. **Subsequent calls**: Returns the same instance with preserved state
3. **Application lifetime**: One instance lives for entire app runtime
4. **Application restart**: Process exit → `_telegram_fallback = None` → fresh state on next startup

### Initialization Timing

| Event | What Happens | State Value |
|-------|-------------|-------------|
| **Application startup** | `get_telegram_fallback()` called for first time | All fields at defaults |
| **Module import** | `TelegramFallback` class defined | No instance yet |
| **First use** | `send_message()` → `get_telegram_fallback()` → `__init__()` | Instance created, state initialized |
| **First failure** | `_handle_send_failure()` under lock | `_has_logged_first_failure = True` |
| **Application restart** | Process exits, new process starts | Fresh instance = fresh state |

### Reset Behavior

| Scenario | Mechanism | Result |
|----------|-----------|--------|
| **Application restart** | Process exits, `_telegram_fallback` goes out of scope | ✅ **Automatic reset** - New process = fresh instance = default state |
| **Manual reset (future)** | Call `reset_first_failure_state()` method | ✅ **Intentional reset** - Set fields back to defaults without restart |
| **Recovery-based reset (future)** | After N consecutive successful sends | ✅ **Conditional reset** - Reset flag when bridge recovers |

**No persistence across restarts is intentional:**
- First-failure detection is per-startup-diagnostic, not persistent state
- Each restart gets a fresh window to detect "is the bridge down right now?"
- If bridge stays down across restarts, each restart logs one WARNING (correct behavior)

### Thread-Safety Implementation

The lock protects the check-and-set sequence:

```python
async def _handle_send_failure(self, error_context: str = ""):
    async with self._first_failure_lock:  # 🔒 Serialize access
        if not self._has_logged_first_failure:
            # First failure - log at WARNING level
            logger.warning(...)
            self._has_logged_first_failure = True  # ✅ Set under lock
            self._first_failure_timestamp = datetime.now()
            self._failure_count = 1
        else:
            # Subsequent failure - log at DEBUG level
            logger.debug(...)
            self._failure_count += 1
        self._last_failure_timestamp = datetime.now()
```

**Why `asyncio.Lock`?**
- Designed for async/await contexts (FastAPI uses async)
- Non-blocking when lock is free
- Serializes the critical section (check + set)
- Minimal overhead: lock acquisition is fast

### State Access Patterns

**Read access (no lock needed for simple reads):**
```python
def get_bridge_status(self) -> dict:
    return {
        "reachable": self._is_reachable,
        "failure_count": self._failure_count,  # Safe to read
        # ...
    }
```

**Write access (always under lock):**
```python
async def _handle_send_failure(self, error_context: str = ""):
    async with self._first_failure_lock:  # 🔒 Required
        # ... modify state ...
```

## Why This Design Works

### 1. Matches Application Architecture
- FastAPI is async → `asyncio.Lock` is native
- Single-process deployment → singleton pattern is natural
- Module-level services → global accessor function

### 2. Correct Lifecycle
- **Initialization**: On first use (lazy)
- **Lifetime**: Application lifetime (singleton)
- **Reset**: On application restart (automatic)

### 3. Thread-Safe by Design
- Lock protects the critical section
- No race conditions possible
- Clear synchronization points

### 4. Testable
```python
# Each test gets a fresh instance
async def test_first_failure_logging():
    fallback = TelegramFallback()  # Fresh instance
    await fallback._handle_send_failure("error")
    assert fallback._has_logged_first_failure == True
```

### 5. Simple and Maintainable
- All state lives in one place (the class that uses it)
- No external dependencies (databases, caches)
- Clear mental model (one instance, one state)

## Implementation Checklist

For the implementation bead:

- [ ] Add `asyncio.Lock` to `TelegramFallback.__init__()`
- [ ] Make `_handle_send_failure()` async (currently sync)
- [ ] Update all call sites to `await self._handle_send_failure(...)`
- [ ] Ensure all state mutations are under lock protection
- [ ] Add tests for concurrent failures (use `asyncio.gather()`)
- [ ] Add test for first-failure flag reset after restart

## Summary

**Storage Location:** Instance variables in `TelegramFallback` class (singleton pattern)

**Rationale:**
1. ✅ Thread-safe with `asyncio.Lock`
2. ✅ Clear lifecycle (init on first use, dies on process exit)
3. ✅ Natural reset on application restart
4. ✅ Accessible globally via `get_telegram_fallback()`
5. ✅ Encapsulated within the class that uses it
6. ✅ Testable (fresh instance per test)
7. ✅ Simple (no external dependencies)

**Rejected Options:**
- Module-level variable (not thread-safe)
- Class attribute (unnecessary complexity)
- Request context (wrong lifecycle)
- Database (wrong lifecycle, overkill)

**Reset Behavior:**
- Automatic reset on application restart (process exit → new instance)
- Future: Manual reset via method call
- Future: Recovery-based reset after N consecutive successes
