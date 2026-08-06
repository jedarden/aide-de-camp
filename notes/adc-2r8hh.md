# First-Failure Tracking Implementation (adc-2r8hh)

## Summary

Implemented a `has_failed_since_startup` flag to track whether any Telegram send has failed since service startup.

## Changes Made

### 1. Added `_has_failed_since_startup` flag to `TelegramFallback` class
- **Location**: `src/telegram/fallback.py`
- **Initial state**: `False` (set in `__init__`)
- **Purpose**: Track if any Telegram send has failed since service startup

### 2. Set flag on first failure
- **Location**: `src/telegram/fallback.py`, `_record_failure_locked` method
- **Logic**: Flag is set to `True` when the first failure after startup occurs
- **Thread safety**: Flag is set under `_first_failure_lock` to prevent race conditions

### 3. Expose flag in status endpoint
- **Location**: `src/telegram/fallback.py`, `get_status` method
- **API**: `get_status()` now returns `has_failed_since_startup` boolean

### 4. Reset support
- **Location**: `src/telegram/fallback.py`, `reset_first_failure_state` method
- **Behavior**: Flag resets to `False` when first failure state is reset (for testing/recovery)

### 5. Added comprehensive tests
- **Location**: `tests/test_telegram_fallback.py`
- **Coverage**:
  - Initial state verification
  - Flag setting on first failure
  - Status exposure
  - Reset behavior
  - Thread safety under concurrent failures

## Acceptance Criteria Met

✅ **Global or service-level flag**: Added `_has_failed_since_startup` as an instance variable on the singleton `TelegramFallback` object

✅ **Resets to False on startup**: Flag is initialized to `False` in `__init__` when service starts

✅ **Sets to True on first failure**: Flag is set to `True` in `_record_failure_locked` on the first failure

✅ **Thread-safe**: Flag is set under `_first_failure_lock`, which serializes access in async/await context

## Usage Example

```python
from src.telegram.fallback import get_telegram_fallback

telegram = get_telegram_fallback()

# Check if any failure has occurred since startup
status = telegram.get_status()
if status["has_failed_since_startup"]:
    print("At least one Telegram send has failed since startup")

# Reset the flag (for testing/recovery)
await telegram.reset_first_failure_state()
```

## Implementation Notes

The flag integrates with the existing first-failure detection infrastructure:
- Uses the same `_first_failure_lock` for thread safety
- Follows the same lifecycle as `_has_logged_first_failure`
- Resets via the same `reset_first_failure_state` method
- Exposed through the same `get_status()` endpoint

This minimal addition provides a simple boolean indicator of failure occurrence without requiring checking counters or timestamps.
