# First-Failure Tracking Mechanism Design

## Problem Statement
Track and detect the **FIRST** Telegram send failure after startup, ensuring that only the first failure logs at WARNING level while all subsequent failures log at DEBUG level to avoid spam.

## Current Implementation (Existing)

Located in `src/telegram/fallback.py`:

```python
class TelegramFallback:
    def __init__(self, bridge_url: str | None = None):
        # ...
        self._has_logged_first_failure = False  # ❌ Not thread-safe

    def _handle_send_failure(self, error_context: str = ""):
        # ...
        if not self._has_logged_first_failure:  # ❌ Race condition here
            logger.warning(f"First Telegram send failure detected...")
            self._has_logged_first_failure = True
        else:
            logger.debug(f"Repeated Telegram send failure...")
```

### Problem with Current Implementation

**Thread-safety issue:** In async FastAPI, multiple requests can execute concurrently:

```
Time  Request A                      Request B
----  ----------------------         ----------------------
T1    if not self._has_logged_first_failure:  # True
T2                                   if not self._has_logged_first_failure:  # True (still!)
T3    self._has_logged_first_failure = True
T4    logger.warning("First failure...")
T5                                   self._has_logged_first_failure = True
T6                                   logger.warning("First failure...")  # ❌ Duplicate!
```

Both requests pass the check before either sets the flag, resulting in **two WARNING logs** instead of one.

## Design Solution: Thread-Safe First-Failure Tracking

### 1. State Storage

**Location:** Module-level, instance variable on `TelegramFallback` singleton

**State variables:**

```python
class TelegramFallback:
    # Use asyncio.Lock for thread-safety in async context
    _first_failure_lock: asyncio.Lock = None
    _has_logged_first_failure: bool = False
```

**Why asyncio.Lock?**
- FastAPI is async, so we need `asyncio.Lock` not `threading.Lock`
- The singleton pattern means one instance shared across all requests
- Lock ensures only one coroutine can check-and-set the flag at a time

### 2. Initialization

```python
def __init__(self, bridge_url: str | None = None):
    # ... existing code ...
    self._first_failure_lock = asyncio.Lock()  # Create lock in __init__
    self._has_logged_first_failure = False
```

**Lock creation in `__init__`:** Each instance gets its own lock. Since we use the singleton pattern via `get_telegram_fallback()`, there's only one instance and thus one lock.

### 3. Thread-Safe Failure Handler

```python
def _handle_send_failure(self, error_context: str = ""):
    """Handle a send failure - log warning only on the first failure after startup.

    Thread-safe: uses asyncio.Lock to ensure only one WARNING log across all concurrent
    failures at startup. Subsequent failures log at DEBUG level.

    Args:
        error_context: Details about the error (status code, error message, etc.)
    """
    import asyncio
    
    self._is_reachable = False
    self._failure_count += 1
    now = datetime.now()
    
    # Thread-safe first-failure tracking
    async def _log_first_failure():
        async with self._first_failure_lock:
            if not self._has_logged_first_failure:
                logger.warning(
                    f"First Telegram send failure detected at {self.bridge_url}. "
                    f"Error: {error_context if error_context else 'unknown error'}. "
                    f"Subsequent failures will be logged at DEBUG level only."
                )
                self._has_logged_first_failure = True
                self._last_failure_logged = now
                return True
            return False
    
    # Run the async check
    was_first = asyncio.run(_log_first_failure())
    
    if not was_first:
        # Subsequent failures - log at DEBUG level to avoid spam
        logger.debug(
            f"Repeated Telegram send failure #{self._failure_count} at {self.bridge_url}. "
            f"Error: {error_context if error_context else 'unknown error'}."
        )
```

**Wait - there's a problem with `asyncio.run()` in an async context!**

### Correction: Proper Async Implementation

Since `_handle_send_failure()` is called from within async methods (`send_message()`), we need to make it async too:

```python
async def _handle_send_failure(self, error_context: str = ""):
    """Handle a send failure - log warning only on the first failure after startup.

    Thread-safe: uses asyncio.Lock to ensure only one WARNING log across all concurrent
    failures at startup. Subsequent failures log at DEBUG level.
    """
    self._is_reachable = False
    self._failure_count += 1
    now = datetime.now()

    # Thread-safe first-failure tracking using lock
    async with self._first_failure_lock:
        if not self._has_logged_first_failure:
            # First failure after startup - log at WARNING level
            logger.warning(
                f"First Telegram send failure detected at {self.bridge_url}. "
                f"Error: {error_context if error_context else 'unknown error'}. "
                f"Subsequent failures will be logged at DEBUG level only."
            )
            self._has_logged_first_failure = True
            self._last_failure_logged = now
        else:
            # Subsequent failures - log at DEBUG level to avoid spam
            logger.debug(
                f"Repeated Telegram send failure #{self._failure_count} at {self.bridge_url}. "
                f"Error: {error_context if error_context else 'unknown error'}."
            )
```

### 4. Usage in send_message()

Update `send_message()` to await the async failure handler:

```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool:
    """Send a message to a Telegram chat."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.bridge_url}/send",
                json={...},
                timeout=10.0,
            )

            if response.status_code == 200:
                logger.info(f"Sent Telegram message to chat {chat_id}")
                self._is_reachable = True
                return True
            else:
                error_msg = f"status {response.status_code} - {response.text}"
                await self._handle_send_failure(error_msg)  # ✅ Now async
                return False

    except httpx.RequestError as e:
        error_msg = f"request error: {e}"
        await self._handle_send_failure(error_msg)  # ✅ Now async
        return False
    except Exception as e:
        error_msg = f"unexpected error: {e}"
        await self._handle_send_failure(error_msg)  # ✅ Now async
        return False
```

## Race Condition Analysis

### With Lock (Thread-Safe)

```
Time  Request A                              Request B
----  --------------------------------------  --------------------------------------
T1    async with self._first_failure_lock:   # A acquires lock
T2    if not self._has_logged_first_failure: # True
T3                                          async with self._first_failure_lock:   # B blocks
T4    logger.warning("First failure...")     # A logs WARNING
T5    self._has_logged_first_failure = True # A sets flag
T6    # exit lock                            # A releases lock
T7                                          # B acquires lock
T8                                          if not self._has_logged_first_failure: # False
T9                                          logger.debug("Repeated failure...")    # B logs DEBUG
T10                                         # exit lock
```

**Result:** Exactly one WARNING log (Request A), one DEBUG log (Request B) ✅

### Without Lock (Current - Broken)

```
Time  Request A                              Request B
----  --------------------------------------  --------------------------------------
T1    if not self._has_logged_first_failure: # True (no lock!)
T2                                          if not self._has_logged_first_failure: # True (still!)
T3    logger.warning("First failure...")     # A logs WARNING
T4    self._has_logged_first_failure = True
T5                                          logger.warning("First failure...")     # B logs WARNING
T6                                          self._has_logged_first_failure = True
```

**Result:** Two WARNING logs ❌

## Implementation Checklist

For the next bead (implementation):

1. ✅ Add `self._first_failure_lock = asyncio.Lock()` to `__init__()`
2. ✅ Make `_handle_send_failure()` an `async` method
3. ✅ Wrap the first-failure check in `async with self._first_failure_lock:`
4. ✅ Update all callers of `_handle_send_failure()` to use `await`
5. ✅ Test concurrent failures to verify only one WARNING log

## Alternative Approaches Considered

### 1. Atomic Flag (`asyncio.Event`)
- **Pros:** Built-in atomic primitive
- **Cons:** Events are for one-shot notification, not state tracking. No good way to "check if set, then set" atomically without race condition.

### 2. Module-level Lock (Not Instance-Level)
- **Pros:** Shared across all instances
- **Cons:** We use singleton pattern anyway; unnecessary complexity. Instance-level lock is correct.

### 3. Thread-Safe Counter with Compare-And-Swap
- **Pros:** Lock-free, performant
- **Cons:** Python doesn't have true CAS; requires locks anyway. Overkill for a boolean flag.

## Conclusion

The proposed design uses `asyncio.Lock` to protect the `_has_logged_first_failure` flag, ensuring that exactly one WARNING log is emitted for the first failure after startup, regardless of concurrent requests. The lock is instance-level on the singleton `TelegramFallback`, initialized in `__init__()`, and used in the async `_handle_send_failure()` method.
