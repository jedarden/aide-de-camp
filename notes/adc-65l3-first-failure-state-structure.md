# First-Failure State Data Structure

## Overview

This document defines the data structure for tracking first-failure state after Telegram send startup in aide-de-camp. The state tracks whether the first failure after application startup has been logged, preventing log spam while ensuring visibility of bridge connectivity issues.

## State Structure Definition

### Location
The state lives as instance variables in the `TelegramFallback` class (`src/telegram/fallback.py`), accessed via the singleton `get_telegram_fallback()`.

### Data Structure

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import asyncio

@dataclass
class FirstFailureState:
    """
    Tracks the first-failure detection state for Telegram sends.
    
    This state ensures that only ONE WARNING-level log is emitted per
    application startup when the Telegram bridge becomes unreachable,
    while all subsequent failures are logged at DEBUG level to avoid spam.
    """
    
    # Primary first-failure flag
    has_logged_first_failure: bool = False
    """
    Whether the first failure after startup has been logged.
    
    - False: No failures detected yet, or state has been reset
    - True: First failure has been logged at WARNING level
    
    This is the primary flag that controls logging behavior:
    - When False: Next failure logs at WARNING level
    - When True: All subsequent failures log at DEBUG level
    
    Reset scenarios:
    - Application restart (automatic via singleton lifecycle)
    - Manual reset via reset_first_failure_state() method (future)
    - Recovery-based reset after N consecutive successes (future)
    """
    
    # Failure tracking
    failure_count: int = 0
    """
    Total number of send failures since application startup.
    
    Increments on every send_message() failure.
    Used for:
    - Status reporting (get_bridge_status())
    - Monitoring and metrics
    - Potential threshold-based escalation (future)
    
    Does NOT reset on first-failure detection — only on application restart
    or explicit reset.
    """
    
    # Timestamps
    first_failure_timestamp: Optional[datetime] = None
    """
    Timestamp of the very first failure after application startup.
    
    Set once when the first failure occurs and never updated again
    (until application restart or explicit reset).
    
    Used for:
    - Diagnostics: "Bridge has been down since X"
    - Metrics: Time-to-detection of bridge issues
    - Correlation with other events
    
    Reset scenarios:
    - Application restart (becomes None again)
    - Manual reset (set back to None)
    """
    
    last_failure_timestamp: Optional[datetime] = None
    """
    Timestamp of the most recent failure.
    
    Updated on every failure (not just the first).
    
    Used for:
    - Status reporting: "Last failure X seconds ago"
    - Health checks: Detect if failures are ongoing or intermittent
    - Cooldown enforcement: Avoid rapid retry loops
    
    Reset scenarios:
    - Never resets to None during application lifetime
    - Always updates to the most recent failure time
    """
    
    # Thread safety
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    """
    Asyncio lock for thread-safe state mutations.
    
    Protects the check-and-set sequence in _handle_send_failure()
    to prevent race conditions when multiple concurrent requests fail.
    
    All state mutations MUST acquire this lock first:
    - has_logged_first_failure = True
    - failure_count += 1
    - first_failure_timestamp assignment
    - last_failure_timestamp assignment
    
    Read operations (get_bridge_status()) do NOT require the lock
    as they read immutable values or don't require consistency.
    """
```

## Integration with TelegramFallback Class

### Instance Initialization

```python
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # ... existing initialization ...
        
        # First-failure tracking state (flat instance variables)
        self._has_logged_first_failure: bool = False
        self._failure_count: int = 0
        self._first_failure_timestamp: Optional[datetime] = None
        self._last_failure_timestamp: Optional[datetime] = None
        self._first_failure_lock: asyncio.Lock = asyncio.Lock()
```

### State Mutation Pattern (Thread-Safe)

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
            self._has_logged_first_failure = True
            self._first_failure_timestamp = datetime.now()
            self._failure_count = 1
            self._last_failure_logged = datetime.now()
        else:
            # Subsequent failure - log at DEBUG level
            logger.debug(
                f"Repeated Telegram send failure #{self._failure_count + 1} "
                f"at {self.bridge_url}. "
                f"Error: {error_context if error_context else 'unknown error'}."
            )
            self._failure_count += 1
            self._last_failure_timestamp = datetime.now()
```

### Read Access Pattern (No Lock Required)

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
        "failure_count": self._failure_count,
        "has_logged_first_failure": self._has_logged_first_failure,
        "first_failure_timestamp": self._first_failure_timestamp.isoformat() 
            if self._first_failure_timestamp else None,
        "last_failure_timestamp": self._last_failure_timestamp.isoformat() 
            if self._last_failure_timestamp else None,
    }
```

## Reset Scenarios

### 1. Automatic Reset on Application Restart

**Mechanism:** Process exit → `_telegram_fallback` goes out of scope → new process → fresh singleton → default state

**What resets:** All fields return to defaults:
- `has_logged_first_failure = False`
- `failure_count = 0`
- `first_failure_timestamp = None`
- `last_failure_timestamp = None`

**Why:** First-failure detection is a per-startup diagnostic. Each restart gets a fresh window to detect "is the bridge down right now?"

**Result:** ✅ **Automatic** — No manual intervention required

### 2. Manual Reset (Future Feature)

**Mechanism:** Call a reset method on the singleton instance

```python
async def reset_first_failure_state(self) -> None:
    """
    Manually reset the first-failure tracking state.
    
    Use cases:
    - After bridge recovery confirmation
    - After manual bridge fix
    - Testing scenarios
    
    Does NOT reset failure_count (keeps running total).
    """
    async with self._first_failure_lock:
        self._has_logged_first_failure = False
        self._first_failure_timestamp = None
        # Keep failure_count and last_failure_timestamp for diagnostics
```

**What resets:**
- `has_logged_first_failure = False`
- `first_failure_timestamp = None`

**What does NOT reset:**
- `failure_count` (keeps running total for diagnostics)
- `last_failure_timestamp` (most recent failure still relevant)

**Result:** ✅ **Intentional** — Explicit action by operator or code

### 3. Recovery-Based Reset (Future Feature)

**Mechanism:** After N consecutive successful sends, reset the flag

```python
async def _handle_send_success(self):
    """Handle a successful send (future method)."""
    async with self._first_failure_lock:
        if self._consecutive_success_count >= self._recovery_threshold:
            self._has_logged_first_failure = False
            self._first_failure_timestamp = None
            self._consecutive_success_count = 0
```

**What resets:** Same as manual reset

**When:** After configurable number of consecutive successes (e.g., 5)

**Why:** If the bridge recovers, allow a new first-failure WARNING on next degradation without requiring restart

**Result:** ✅ **Conditional** — Automatic but based on recovery detection

## State Lifecycle Diagram

```
Application Startup
    │
    ├─► get_telegram_fallback() called
    │   └─► TelegramFallback() instance created
    │       └─► All state fields at defaults
    │           ├─► has_logged_first_failure = False
    │           ├─► failure_count = 0
    │           ├─► first_failure_timestamp = None
    │           └─► last_failure_timestamp = None
    │
    ├─► First send_message() failure occurs
    │   └─► _handle_send_failure() under lock
    │       ├─► Check: has_logged_first_failure == False?
    │       ├─► YES → Log WARNING, set flag
    │       │   ├─► has_logged_first_failure = True
    │       │   ├─► first_failure_timestamp = now
    │       │   ├─► failure_count = 1
    │       │   └─► last_failure_timestamp = now
    │       │
    │       └─► User sees WARNING in logs
    │
    ├─► Subsequent failures
    │   └─► _handle_send_failure() under lock
    │       ├─► Check: has_logged_first_failure == True?
    │       ├─► YES → Log DEBUG only, increment counter
    │       │   ├─► failure_count += 1
    │       │   └─► last_failure_timestamp = now
    │       │
    │       └─► User sees DEBUG logs (no WARNING spam)
    │
    ├─► Application restart (process exit)
    │   └─► New process → fresh singleton → all defaults
    │       └─► Next failure logs WARNING again
    │
    └─► Manual reset (future)
        └─► reset_first_failure_state() called
            └─► Flag resets → next failure logs WARNING
```

## Usage Examples

### Example 1: Normal Operation (Bridge Up)

```python
# Startup: all fields at defaults
fallback = get_telegram_fallback()
assert fallback._has_logged_first_failure == False
assert fallback._failure_count == 0

# Send succeeds → no state changes
await fallback.send_message(chat_id, "Hello")
assert fallback._has_logged_first_failure == False  # unchanged
assert fallback._failure_count == 0  # unchanged
```

### Example 2: Bridge Failure Scenario

```python
# First failure occurs
await fallback.send_message(chat_id, "Test")
# → Logs WARNING (first failure detected)
# → State updated under lock:
#    has_logged_first_failure = True
#    failure_count = 1
#    first_failure_timestamp = 2026-07-02T14:30:00Z
#    last_failure_timestamp = 2026-07-02T14:30:00Z

# Subsequent failures (10 more concurrent requests)
await asyncio.gather(*[fallback.send_message(chat_id, f"msg{i}") for i in range(10)])
# → Logs 10 DEBUG messages (no WARNING spam)
# → State updated:
#    failure_count = 11
#    last_failure_timestamp = 2026-07-02T14:31:45Z
#    first_failure_timestamp = unchanged (still 14:30:00Z)

# Check status
status = fallback.get_bridge_status()
assert status["failure_count"] == 11
assert status["has_logged_first_failure"] == True
assert status["first_failure_timestamp"] == "2026-07-02T14:30:00+00:00"
```

### Example 3: Application Restart

```python
# Before restart: failure_count = 11, flag = True
# Application restarts (process exit, new process)
# After restart: fresh singleton
fallback = get_telegram_fallback()
assert fallback._has_logged_first_failure == False  # Reset!
assert fallback._failure_count = 0  # Reset!
assert fallback._first_failure_timestamp is None  # Reset!

# Next failure logs WARNING again (new first-failure detection)
await fallback.send_message(chat_id, "Test after restart")
# → Logs WARNING (first failure of new startup)
```

## Type Safety

All fields use proper type hints for static analysis:

```python
from typing import Optional

has_logged_first_failure: bool              # Always True or False
failure_count: int                          # Always non-negative integer
first_failure_timestamp: Optional[datetime]  # datetime or None
last_failure_timestamp: Optional[datetime]  # datetime or None
_first_failure_lock: asyncio.Lock          # Always a Lock instance
```

## Future Extensions

The state structure is designed to support future enhancements:

### 1. Error Type Tracking

```python
# Add field to track error categories
first_failure_error_type: Optional[str] = None  # e.g., "timeout", "connection_refused", "5xx_error"
```

### 2. Channel-Specific Tracking (Multi-Bridge)

```python
# Add field to track which channel failed
first_failure_channel: Optional[str] = None  # e.g., "telegram-claude-bridge", "fallback-bridge"
```

### 3. Recovery Threshold

```python
# Add fields for recovery-based reset
consecutive_success_count: int = 0
recovery_threshold: int = 5  # Reset after 5 consecutive successes
```

## Summary

**State Structure:**
- `has_logged_first_failure: bool` — Primary flag (False → True, once per startup)
- `failure_count: int` — Total failures since startup
- `first_failure_timestamp: Optional[datetime]` — Timestamp of first failure
- `last_failure_timestamp: Optional[datetime]` — Timestamp of most recent failure
- `_first_failure_lock: asyncio.Lock` — Thread-safety for mutations

**Storage:** Instance variables in `TelegramFallback` singleton

**Reset Scenarios:**
- ✅ Application restart (automatic, all fields)
- ✅ Manual reset (future, selective fields)
- ✅ Recovery-based reset (future, selective fields)

**Thread-Safety:** All mutations protected by `asyncio.Lock`

**Type Safety:** All fields properly typed for static analysis
