# adc-2ju7: Add WARNING log on first Telegram send failure

## Status: VERIFIED COMPLETE

Implementation completed in commit `c45a963`.

## Implementation Verification

The `_handle_send_failure()` method in `src/telegram/fallback.py` (lines 198-225) implements:

### ✅ Acceptance Criteria 1: First send failure logs a WARNING with context
- **Line 45**: `self._has_logged_first_failure = False` - initialization tracks first failure state
- **Lines 211-217**: On first failure, logs at WARNING level with full context:
  ```python
  logger.warning(
      f"First Telegram send failure detected at {self.bridge_url}. "
      f"Error: {error_context if error_context else 'unknown error'}. "
      f"Subsequent failures will be logged at DEBUG level only."
  )
  ```

### ✅ Acceptance Criteria 2: Log includes error type and message
Error context is passed from all three failure paths in `send_message()`:
- **Line 83**: HTTP status errors → `"status {response.status_code} - {response.text}"`
- **Line 88**: Request errors → `"request error: {e}"`
- **Line 92**: Unexpected errors → `"unexpected error: {e}"`

### ✅ Acceptance Criteria 3: No duplicate logs for the same initial failure
- **Line 211**: Condition `if not self._has_logged_first_failure:` ensures only first failure triggers WARNING
- **Line 218**: `self._has_logged_first_failure = True` prevents re-logging
- **Lines 221-224**: Subsequent failures logged at DEBUG level only

## Implementation Details

- **File**: `src/telegram/fallback.py`
- **Method**: `_handle_send_failure(self, error_context: str = "")`
- **State tracking**: `_has_logged_first_failure` boolean flag
- **Log levels**: WARNING (first failure only), DEBUG (all subsequent failures)
- **Error context**: Passed from caller, includes error type and message

## Code Review Summary

The implementation correctly:
- Tracks first-failure state via `_has_logged_first_failure` boolean
- Logs detailed error context including error type and message
- Prevents duplicate WARNING logs for the same initial failure
- Falls back to DEBUG logging for repeated failures to avoid log spam

✅ All acceptance criteria met. Implementation complete and verified.
