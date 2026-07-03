# adc-2duz: First-Failure State Storage Design

## Task
Design WHERE the first-failure state lives in the async FastAPI application.

## Outcome

### Storage Location: Class Attribute ✅

**Implementation**: `TelegramFallback._first_failure_state: FirstFailureState`

**Pattern**: Instance variable on singleton class (accessed via `get_telegram_fallback()`)

**Rationale**:
- Thread-safe with `asyncio.Lock` for atomic state transitions
- Easy to test (instantiate, reset, mock)
- Encapsulated state (not global variable)
- Consistent with existing patterns (`_ambient_monitor` in `monitoring/ambient.py`)

### Initialization: Lazy Loading

**Timing**: On first call to `get_telegram_fallback()` after startup

**Why**:
- Faster application startup
- Only initialize when actually needed
- Fail-fast when first used (not during import)

### Reset Behavior

1. **Automatic reset on startup** ✅
   - All fields reset to defaults on application restart
   - This is desired: "first failure after startup" is per-process

2. **Manual reset** (if needed)
   - Simplest: application restart
   - Advanced: admin API endpoint to reset state at runtime

3. **No auto-reset after notification** ⚠️
   - State persists after first-failure notification
   - Prevents notification spam on subsequent failures

### Persistence: In-Memory Only

**Does NOT survive restarts** (by design)

**Why**:
- "First failure after startup" is inherently process-scoped
- Clear semantics: `has_failed=False` means "clean since this startup"
- Simplicity: no database schema, migrations, or cleanup
- Optional persistence available via env var (`ADC_FIRST_FAILURE_DB`) for historical tracking (not runtime state)

### Thread-Safety

**Protection**: `asyncio.Lock` on `TelegramFallback._state_lock`

**Why**:
- Prevents race conditions on concurrent first-failure detection
- Atomic check-and-set operations
- Minimal overhead (microseconds)
- Compatible with async/await throughout

## Dependencies

- ✅ **adc-65l3**: Data structure design (`FirstFailureState` dataclass)
- ✅ **adc-4vhr**: Tracking mechanism design (thread-safety strategy)

## Documentation

Full design: `docs/first-failure-state-storage.md`

## Acceptance Criteria

- ✅ Storage location documented with rationale
- ✅ Initialization timing explained
- ✅ Reset behavior explained (startup vs manual)
- ✅ Depends on adc-65l3 (data structure) - COMPLETE

---

**Bead**: adc-2duz  
**Status**: ✅ Complete  
**Date**: 2026-07-02
