# Bead adc-hyqc: Telegram Send Failure WARNING

## Finding

The functionality requested in this bead **already exists** in `src/telegram/fallback.py`.

## Existing Implementation

The `_handle_send_failure()` method (lines 197-212) implements exactly what was requested:

```python
def _handle_send_failure(self):
    """Handle a send failure - log warning only on first failure in a batch."""
    self._is_reachable = False
    self._failure_count += 1

    # Only log a warning if we haven't logged recently (within last 60 seconds)
    # or if this is the first failure
    now = datetime.now()
    if (self._last_failure_logged is None or
        (now - self._last_failure_logged).total_seconds() > 60):
        logger.warning(
            f"Telegram bridge unreachable at {self.bridge_url} "
            f"(failure count: {self._failure_count}). "
            f"Subsequent failures will be logged at DEBUG level only."
        )
        self._last_failure_logged = now
```

## How It Works

1. **First failure after startup**: `_last_failure_logged` is `None`, so a WARNING is logged
2. **Subsequent failures**: Only logged if 60+ seconds have passed since the last WARNING
3. **All error paths covered**:
   - HTTP non-200 response (line 80)
   - `httpx.RequestError` network errors (line 87)
   - Generic exceptions (line 91)

## Acceptance Criteria Met

- ✅ First send failure logs a WARNING with context (bridge URL + failure count)
- ✅ Failures are visible at WARNING level (not just DEBUG)
- ✅ No log spam from repeated failures (60-second rate limit)

## Conclusion

No code changes needed. The implementation was already present and working as intended.
