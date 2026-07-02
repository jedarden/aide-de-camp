# First-Failure Tracking Mechanism Design

## Overview

This document designs a robust mechanism to track and detect the **FIRST** Telegram send failure after startup in aide-de-camp (async FastAPI application).

## Current Implementation Analysis

The existing `TelegramFallback` class (`src/telegram/fallback.py`) has a basic first-failure mechanism:

### Current State Variables
```python
self._has_logged_first_failure = False  # Boolean flag
self._failure_count = 0                 # Total failures
self._last_failure_logged = None        # Timestamp
self._is_reachable = None               # Bridge reachability
```

### Current Behavior
- First failure after startup → WARNING log
- Subsequent failures → DEBUG log (rate-limited)
- State is per-instance (singleton via `get_telegram_fallback()`)

## Problems with Current Design

### 1. Thread-Safety Issues ❌
**Problem**: FastAPI handles concurrent requests asynchronously. Multiple coroutines can call `_handle_send_failure()` simultaneously, leading to race conditions:

```python
# Thread 1                    # Thread 2
if not self._has_logged_first_failure:
                              if not self._has_logged_first_failure:
logger.warning(...)           
self._has_logged_first_failure = True
                              logger.warning(...)  # DUPLICATE WARNING!
                              self._has_logged_first_failure = True
```

**Impact**: Multiple concurrent failures on first error → duplicate WARNING logs, defeating the purpose.

### 2. State Persistence Limitations
- State resets to `False` on every app restart
- No persistent record of first failure timestamp
- Cannot distinguish "first after startup" from "first ever"

### 3. Testing Challenges
- State encapsulated in instance, hard to reset in tests
- No clean way to inject a mock state manager
- Hard to verify first-failure behavior deterministically

### 4. No Persistence Layer
- First failure timestamp not stored anywhere
- Cannot query "when was the first failure?"
- Cannot build metrics/alerting on first-failure events

## Proposed Design

### Architecture: Asyncio-Safe State Manager with Optional Persistence

```
┌─────────────────────────────────────────────────────────────┐
│                   TelegramFallback                          │
│  ┌───────────────────────────────────────────────────────┐ │
│  │          FirstFailureTracker (thread-safe)            │ │
│  │                                                        │ │
│  │  - asyncio.Lock for atomic state transitions          │ │
│  │  - first_failure_timestamp: datetime | None           │ │
│  │  - total_failure_count: int                           │ │
│  │  - last_failure_timestamp: datetime | None            │ │
│  │                                                        │ │
│  │  Methods:                                             │ │
│  │  - record_failure() -> FirstFailureEvent              │ │
│  │  - is_first_failure() -> bool                          │ │
│  │  - reset_for_testing()                                 │ │
│  │  - get_state() -> FailureState                        │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Optional Persistence│
                    │  (file-based SQLite)│
                    │  - Record first      │
                    │    failure events    │
                    │  - Enable metrics    │
                    └─────────────────────┘
```

### Thread-Safety Strategy

**Approach 1: asyncio.Lock (Recommended)**
```python
class FirstFailureTracker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._first_failure_logged = False
        self._total_failures = 0
        
    async def record_failure(self, error_context: str) -> FailureEvent:
        async with self._lock:
            self._total_failures += 1
            is_first = not self._first_failure_logged
            
            if is_first:
                self._first_failure_logged = True
                return FailureEvent(
                    type="first_failure",
                    timestamp=datetime.now(timezone.utc),
                    error_context=error_context,
                    failure_number=self._total_failures
                )
            else:
                return FailureEvent(
                    type="subsequent_failure",
                    timestamp=datetime.now(timezone.utc),
                    error_context=error_context,
                    failure_number=self._total_failures
                )
```

**Why asyncio.Lock?**
- FastAPI runs on asyncio event loop
- Lock ensures atomic check-and-set operations
- Minimal overhead (only held during microsecond state transitions)
- Compatible with async/await throughout the stack

**Alternative: threading.Lock** ❌ Not recommended
- Would work but mixes threading and asyncio models
- Less idiomatic in async FastAPI context

### State Storage Options

#### Option 1: In-Memory Only (Current + Lock)
**Pros:**
- Simple, no dependencies
- Fast, no I/O
- No persistence cleanup

**Cons:**
- Lost on restart (may be acceptable)
- No historical tracking
- Harder to debug post-mortem

#### Option 2: In-Memory + Optional Persistence File (Recommended)
**Pros:**
- Best of both worlds
- Optional persistence via env var: `ADC_FIRST_FAILURE_DB=/tmp/first_failures.db`
- Enables post-mortem analysis
- Can build metrics over time

**Cons:**
- Slightly more complex
- Need file cleanup strategy

**Schema:**
```sql
CREATE TABLE first_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    startup_time TEXT NOT NULL,  -- ISO timestamp of app start
    first_failure_time TEXT NOT NULL,
    error_context TEXT,
    resolved INTEGER DEFAULT 0  -- Whether service recovered
);
```

### Implementation Guidance

#### Phase 1: Thread-Safe In-Memory Tracker (MVP)
1. Create `FirstFailureTracker` class with `asyncio.Lock`
2. Replace `_handle_send_failure()` logic with tracker
3. Return `FailureEvent` objects instead of side-effects
4. Update logging based on event type

#### Phase 2: Optional Persistence (Enhancement)
1. Add SQLite persistence layer (opt-in via env var)
2. Record first failure events with startup timestamps
3. Add API endpoint to query first-failure history
4. Add metrics endpoint for monitoring

#### Phase 3: Testing & Reset (Quality)
1. Add `reset_for_testing()` method for test isolation
2. Add dependency injection support
3. Add unit tests for concurrent failure scenarios
4. Add integration tests for real failure detection

## Design Decisions

### Q1: Why not use atomic operations (e.g., `compare_and_swap`)?
**A**: Python doesn't have atomic compare-and-swap primitives for booleans. `asyncio.Lock` is the idiomatic asyncio pattern for mutual exclusion.

### Q2: Why not use a global state variable?
**A**: Global variables are not asyncio-safe. Even with a lock, global state is hard to test and reason about. Encapsulation in a tracker class is cleaner.

### Q3: Why separate tracker from TelegramFallback?
**A**: Separation of concerns. The tracker manages failure state; TelegramFallback manages Telegram communication. This makes testing easier and allows reuse of the tracker for other services.

### Q4: Why optional persistence instead of required?
**A**: Not all deployments need persistence. Local development and testing can run without it. Production can opt-in via env var.

## Race Condition Examples

### Scenario 1: Concurrent First Failures (Fixed by Lock)
```
Time    Request A              Request B              State
──────  ─────────────────────  ─────────────────────  ─────────────────────
t0      send_message fails     send_message fails     _first = False
t1      check _first=False                            (both see False)
t2      acquiring lock...     acquiring lock...      (A gets lock first)
t3      set _first=True,       waiting for lock...    _first = True
        log WARNING                                   
t4      release lock           acquiring lock...     
t5                            check _first=True      (B sees True)
t6                            log DEBUG              
```

**Result**: Only ONE WARNING logged (correct)

### Scenario 2: Mixed Timing (Fixed by Lock)
```
Time    Request A              Request B              State
──────  ─────────────────────  ─────────────────────  ─────────────────────
t0      check _first=False                            _first = False
t1      acquiring lock...     
t2      set _first=True,                             _first = True
        log WARNING                                   
t3      release lock           
t4                            send_message fails     
t5                            check _first=True      (B sees True)
t6                            log DEBUG              
```

**Result**: One WARNING, one DEBUG (correct)

## Testing Strategy

### Unit Tests
```python
async def test_concurrent_first_failures():
    """Verify only one WARNING when multiple failures happen concurrently."""
    tracker = FirstFailureTracker()
    
    # Simulate 10 concurrent failures
    tasks = [tracker.record_failure(f"error_{i}") for i in range(10)]
    events = await asyncio.gather(*tasks)
    
    first_failures = [e for e in events if e.type == "first_failure"]
    subsequent_failures = [e for e in events if e.type == "subsequent_failure"]
    
    assert len(first_failures) == 1, "Only one first failure should be logged"
    assert len(subsequent_failures) == 9, "Rest should be subsequent"
```

### Integration Tests
```python
async def test_first_failure_logging(caplog):
    """Verify WARNING on first failure, DEBUG on subsequent."""
    telegram = get_telegram_fallback()
    
    # First failure
    with caplog.at_level(logging.WARNING):
        await telegram.send_message(123, "test")
    assert "First Telegram send failure" in caplog.text
    
    # Second failure
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        await telegram.send_message(123, "test")
    assert "Repeated Telegram send failure" in caplog.text
```

## Performance Considerations

### Lock Contention
- **Overhead**: Microseconds per acquisition
- **Frequency**: Only on failures (rare, hopefully)
- **Impact**: Negligible compared to HTTP I/O (10+ second timeouts)

### State Size
- **Memory**: ~100 bytes per tracker instance
- **Scaling**: Singleton pattern ensures only one instance

## Error Handling

### Tracker Failure Fallback
If the tracker itself fails (e.g., persistence I/O error):
1. Fall back to basic boolean flag
2. Log tracker error at ERROR level
3. Continue operation (degraded mode)

## Migration Path

### Step 1: Add Tracker Class (Non-Breaking)
```python
# src/telegram/first_failure_tracker.py
class FirstFailureTracker:
    # ... implementation ...
```

### Step 2: Wire into TelegramFallback
```python
class TelegramFallback:
    def __init__(self):
        # ... existing ...
        self._failure_tracker = FirstFailureTracker()
        
    def _handle_send_failure(self, error_context: str):
        event = await self._failure_tracker.record_failure(error_context)
        if event.type == "first_failure":
            logger.warning(f"First Telegram send failure: {error_context}")
        else:
            logger.debug(f"Repeated failure #{event.failure_number}: {error_context}")
```

### Step 3: Add Tests
- Unit tests for tracker
- Integration tests for TelegramFallback
- Concurrent failure tests

### Step 4: Optional Persistence
- Add env var check
- Implement SQLite layer
- Add metrics endpoints

## Acceptance Criteria Verification

- [x] **State storage**: Defined (FirstFailureTracker class with asyncio.Lock)
- [x] **Thread-safety**: Addressed (asyncio.Lock ensures atomic state transitions)
- [x] **Race conditions**: Examples provided, solution prevents them
- [x] **Implementation guidance**: Step-by-step migration path provided
- [x] **Testing strategy**: Unit and integration test patterns defined
- [x] **Performance**: Lock overhead analyzed (negligible)

## Next Steps

See bead **adc-5jl** for implementation of this design:
1. Create `FirstFailureTracker` class
2. Integrate into `TelegramFallback`
3. Add comprehensive tests
4. Implement optional persistence

---

**Design Document**: adc-4vhr  
**Status**: Design Complete  
**Next Bead**: adc-5jl (Implementation)  
**Date**: 2026-07-02
