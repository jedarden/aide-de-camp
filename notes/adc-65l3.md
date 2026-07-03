# First-Failure State Data Structure

## Overview

This document defines the data structure for tracking first-failure state after Telegram send startup in the aide-de-camp FastAPI application.

## Data Structure Definition

### Location and Scope

**Storage Location:** Per-instance state in `TelegramFallback` class

**Scope:** Module-level singleton via `get_telegram_fallback()` - one instance per application lifetime

### State Fields

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import asyncio

@dataclass
class FirstFailureState:
    """
    Immutable snapshot of first-failure tracking state.
    
    Used for debugging, monitoring, and testing.
    """
    has_logged_first_failure: bool  # Whether first failure has been logged
    failure_count: int               # Total number of failures since startup
    first_failure_timestamp: Optional[datetime]  # When first failure occurred
    last_failure_timestamp: Optional[datetime]  # When most recent failure occurred
    bridge_url: str                  # The bridge URL being monitored
```

### Instance Variables (Live State)

The actual state is stored as instance variables in `TelegramFallback.__init__()`:

```python
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # ... existing initialization ...
        
        # First-failure tracking state
        self._has_logged_first_failure: bool = False
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None
        self._last_failure_timestamp: Optional[datetime] = None
        
        # Thread-safety for async FastAPI context
        self._first_failure_lock: asyncio.Lock = asyncio.Lock()
```

### Field-by-Field Documentation

| Field | Type | Purpose | Default | Reset Behavior |
|-------|------|---------|---------|----------------|
| `_has_logged_first_failure` | `bool` | Flag indicating whether the first failure has been logged at WARNING level | `False` | Resets to `False` on application restart |
| `_failure_count` | `int` | Counter for total failures since startup (used for debug logging) | `0` | Resets to `0` on application restart |
| `_first_failure_timestamp` | `Optional[datetime]` | Timestamp of the very first failure after startup | `None` | Resets to `None` on application restart |
| `_last_failure_timestamp` | `Optional[datetime]` | Timestamp of the most recent failure | `None` | Resets to `None` on application restart |
| `_first_failure_lock` | `asyncio.Lock` | Async lock protecting first-failure flag for thread-safety | `asyncio.Lock()` | New lock created on each instance creation |

## Thread-Safety Mechanism

**Why `asyncio.Lock`?**

The FastAPI application serves concurrent async requests. Without synchronization:

```
Request A: check flag (False) → logs WARNING → sets flag (True)
Request B: check flag (still False!) → logs WARNING → sets flag (True)
Result: TWO WARNING logs ❌
```

With `asyncio.Lock`:

```
Request A: acquire lock → check flag (False) → log WARNING → set flag → release lock
Request B: wait for lock → acquire lock → check flag (now True) → log DEBUG → release lock
Result: ONE WARNING log ✅
```

## State Lifecycle

### Initialization (Application Startup)

```python
# In TelegramFallback.__init__()
self._has_logged_first_failure = False
self._failure_count = 0
self._first_failure_timestamp = None
self._last_failure_timestamp = None
self._first_failure_lock = asyncio.Lock()
```

### On First Failure

```python
async def _handle_send_failure(self, error_context: str):
    async with self._first_failure_lock:
        if not self._has_logged_first_failure:
            # First failure - log at WARNING level
            logger.warning(f"First Telegram send failure detected...")
            self._has_logged_first_failure = True
            self._first_failure_timestamp = datetime.now()
            self._last_failure_timestamp = datetime.now()
            self._failure_count = 1
        else:
            # Subsequent failure - log at DEBUG level
            logger.debug(f"Repeated Telegram send failure #{self._failure_count}...")
            self._last_failure_timestamp = datetime.now()
            self._failure_count += 1
```

### On Subsequent Failures

The lock is still acquired (for safety), but the flag is already `True`, so only DEBUG logging occurs and the counter increments.

### Reset Scenarios

| Scenario | Reset Mechanism | Fields Affected |
|----------|----------------|-----------------|
| **Application Restart** | Process exit/restart | ALL fields reset to defaults |
| **Manual Reset** (future) | `reset_first_failure_state()` method | `_has_logged_first_failure = False`, counters to `0` |
| **Recovery-based Reset** (future) | After N consecutive successes | `_has_logged_first_failure = False` (optional feature) |

## Usage Example

```python
# Getting state snapshot for monitoring/health checks
def get_first_failure_state(self) -> FirstFailureState:
    """Return an immutable snapshot of current first-failure state."""
    return FirstFailureState(
        has_logged_first_failure=self._has_logged_first_failure,
        failure_count=self._failure_count,
        first_failure_timestamp=self._first_failure_timestamp,
        last_failure_timestamp=self._last_failure_timestamp,
        bridge_url=self.bridge_url,
    )
```

## Monitoring Integration

The state structure enables health check endpoints:

```python
# In FastAPI app
@app.get("/health/telegram")
async def telegram_health():
    fallback = get_telegram_fallback()
    state = fallback.get_first_failure_state()
    
    return {
        "bridge_reachable": state.has_logged_first_failure == False or state.failure_count == 0,
        "failure_count": state.failure_count,
        "first_failure_at": state.first_failure_timestamp.isoformat() if state.first_failure_timestamp else None,
        "last_failure_at": state.last_failure_timestamp.isoformat() if state.last_failure_timestamp else None,
    }
```

## Summary

The first-failure state data structure consists of:

1. **Core state fields** (4 fields):
   - `bool` flag for first-failure detection
   - `int` counter for total failures
   - `Optional[datetime]` timestamps for first and last failures
   
2. **Synchronization primitive**:
   - `asyncio.Lock` for thread-safety in async FastAPI context

3. **Lifecycle**:
   - Initialized on application startup
   - Modified on send failures (under lock protection)
   - Resets naturally on application restart
   - Can optionally support manual/recovery-based resets

This design ensures exactly one WARNING log per startup sequence while maintaining diagnostic metadata for monitoring and debugging.
