# First-Failure State Data Structure

## Overview

This document defines the data structure for tracking the first Telegram send failure after application startup. The state prevents duplicate notifications while maintaining diagnostic information.

## State Structure

```python
@dataclass
class FirstFailureState:
    """Tracks the first Telegram send failure after startup.
    
    This state is used to detect and report only the FIRST failure,
    preventing notification spam on subsequent send failures.
    """
    # Has the first failure been recorded?
    has_failed: bool = False
    
    # When did the first failure occur?
    first_failure_at: Optional[datetime] = None
    
    # Which channel failed?
    channel_id: Optional[str] = None
    
    # What was the error?
    error_type: Optional[str] = None  # e.g., "TelegramError", "TimeoutError"
    error_message: Optional[str] = None
    
    # Total failure count (for diagnostics)
    total_failures: int = 0
    
    # Have we sent the notification about this first failure?
    notification_sent: bool = False
    
    # When did we send the notification?
    notification_sent_at: Optional[datetime] = None
```

## Field Descriptions

### Core State

- **`has_failed: bool`** — Sentinel flag indicating whether ANY failure has occurred since startup. This is the primary field checked before triggering "first failure" logic.

- **`first_failure_at: Optional[datetime]`** — Timestamp of the first failure occurrence. Set once on the first failure, never updated. Use UTC timezone-aware datetimes.

- **`channel_id: Optional[str]`** — The Telegram channel ID that failed on the first occurrence. Useful for diagnosing whether a specific channel is problematic.

### Error Information

- **`error_type: Optional[str]`** — Exception class name (e.g., `"TelegramError"`, `"ConnectionError"`). Helps categorize the failure type.

- **`error_message: Optional[str]`** — The error message or summary. Useful for quick diagnosis without digging through logs.

### Diagnostics

- **`total_failures: int`** — Monotonically increasing counter of ALL failures since startup. Helps assess failure frequency even after the first failure notification.

### Notification Tracking

- **`notification_sent: bool`** — Prevents duplicate notifications. Set to `True` after the first-failure alert is sent.

- **`notification_sent_at: Optional[datetime]`** — Timestamp of when the notification was sent. Useful for audit trails and debugging.

## Reset Scenarios

### 1. Application Startup (Automatic)

```python
# At module load time in src/monitoring/ambient.py
first_failure_state = FirstFailureState()
```

All fields default to their initial values (fresh state).

### 2. Manual Reset (Admin Action)

If an admin manually resolves a Telegram issue and wants to reset failure tracking:

```python
first_failure_state = FirstFailureState()  # Fresh instance
```

Or selectively:

```python
first_failure_state.has_failed = False
first_failure_state.first_failure_at = None
first_failure_state.notification_sent = False
# Keep total_failures for historical context, or reset to 0
```

### 3. No Auto-Reset After Notification

**IMPORTANT:** The state does NOT automatically reset after sending the first-failure notification. This prevents notification spam if failures continue. The state persists until application restart.

## Thread-Safety Considerations

Since adc is an async FastAPI application, multiple Telegram sends may execute concurrently. The state update MUST be atomic:

```python
# Pattern: Check-and-set in one operation
if not first_failure_state.has_failed:
    # This entire block should be protected by a lock if running in threaded context
    first_failure_state.has_failed = True
    first_failure_state.first_failure_at = datetime.now(timezone.utc)
    first_failure_state.channel_id = channel_id
    first_failure_state.error_type = type(error).__name__
    first_failure_state.error_message = str(error)
    first_failure_state.total_failures += 1
    await send_first_failure_notification(...)
    first_failure_state.notification_sent = True
    first_failure_state.notification_sent_at = datetime.now(timezone.utc)
else:
    # Subsequent failures — just increment counter
    first_failure_state.total_failures += 1
    log_failure(error, channel_id)  # No notification
```

## Implementation Location

The state instance should live at module level in `src/monitoring/ambient.py`:

```python
# src/monitoring/ambient.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

@dataclass
class FirstFailureState:
    # ... (as defined above)

# Module-level singleton
first_failure_state = FirstFailureState()
```

This ensures:
1. Single source of truth across all ambient monitoring checks
2. State persists across requests (in-memory, per-process)
3. Reset on each uvicorn worker startup (expected behavior)

## Usage Pattern

```python
# In the Telegram send error handler
if not first_failure_state.has_failed:
    # First failure! Record and notify
    first_failure_state.has_failed = True
    first_failure_state.first_failure_at = datetime.now(timezone.utc)
    first_failure_state.channel_id = channel_id
    first_failure_state.error_type = type(error).__name__
    first_failure_state.error_message = str(error)[:500]  # Truncate if needed
    first_failure_state.total_failures += 1
    
    await send_first_failure_notification(
        channel_id=first_failure_state.channel_id,
        error_type=first_failure_state.error_type,
        error_message=first_failure_state.error_message,
        failed_at=first_failure_state.first_failure_at
    )
    
    first_failure_state.notification_sent = True
    first_failure_state.notification_sent_at = datetime.now(timezone.utc)
else:
    # Subsequent failure — just count it
    first_failure_state.total_failures += 1
    logger.warning(
        f"Subsequent Telegram send failure (total: {first_failure_state.total_failures}): "
        f"{type(error).__name__}: {error}"
    )
```

## Data Validation

- **`channel_id`** — Should be a valid Telegram channel ID string (e.g., `@channelname` or numeric ID)
- **`error_type`** — Should be the exception class name, not the full qualified path
- **`error_message`** — Consider truncating to ~500 chars to prevent excessive storage/logging
- **Timestamps** — Always use timezone-aware UTC datetimes

## Future Extensions

Potential enhancements not in v1:

- **`last_failure_at: Optional[datetime]`** — Track when the MOST RECENT failure occurred (for health checks)
- **`consecutive_failures: int`** — Track consecutive vs. total failures (reset on success)
- **`failure_history: list[FailureRecord]`** — Keep last N failures for pattern analysis
- **`recovery_at: Optional[datetime]`** — Timestamp of first successful send after failure
