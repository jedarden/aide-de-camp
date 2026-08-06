# Thread-Safety Design for Async FastAPI Application

## Executive Summary

**Design Approach: Minimal Locking with Asyncio Primitives**

This design adopts a **minimal-locking approach** for the aide-de-camp FastAPI application, recognizing that FastAPI runs on a **single-threaded async event loop** rather than using pre-emptive multi-threading. Thread-safety concerns are primarily about cooperative concurrency rather than race conditions from simultaneous thread execution.

**Key Principle:** The application already has strong isolation between concurrent requests through async/await patterns. Most "thread-safety" concerns are actually about **async coroutine safety** and **proper async resource management**.

## Architecture Analysis

### Current Concurrency Model

```python
# FastAPI runs on a single-threaded event loop
# Multiple requests are handled via async/await, not threading
# Context switches only happen at explicit await points

@app.post("/dispatch")
async def dispatch(request: DispatchRequest):
    # Request 1 runs until first await
    result = await classify_utterance(...)  # Potential context switch
    # Control may yield to Request 2 here
    return await process_intent(result)
```

**Key Insight:** Two concurrent requests never execute Python code simultaneously. They take turns at await points.

### Current Thread-Safety Posture

| Component | Current Safety | Risk Level | Mitigation |
|-----------|--------------|-----------|------------|
| SQLite (WAL mode) | Safe (readers) | Low | Use aiosqlite for async DB access |
| Global singletons | Mostly safe | Medium | Lazy initialization needs protection |
| Intent cache | Safe (single-threaded) | Low | TTL-based cleanup already handles |
| SSE broadcaster | Safe (async queues) | Low | Already uses asyncio.Queue |
| Fetch orchestrator | Safe (isolated coroutines) | Low | No shared mutable state |

## Race Condition Analysis

### 1. First-Failure State Tracking

**Scenario:** Multiple fetch sources fail simultaneously

```python
# Current implementation in orchestrator.py
async def execute_with_timeout(source, required, timeout, task):
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        return source, required, result
    except asyncio.TimeoutError:
        # No race condition - each source tracks its own failure
        return source, required, SourceResult(status="timeout", ...)
```

**Analysis:** ✅ **No Race Condition**
- Each fetch source runs in an isolated coroutine
- Failure state is tracked per-source, not globally
- `asyncio.gather()` provides isolation between concurrent operations

**Verdict:** Current implementation is safe. No locking needed.

### 2. Global Singleton Initialization

**Scenario:** Multiple requests initialize global singletons simultaneously

```python
# Current pattern in multiple modules
_store: SessionStore | None = None

def get_store(db_path: Path | None = None) -> SessionStore:
    global _store
    if _store is None:  # ❌ Potential race condition
        _store = SessionStore(db_path or DEFAULT_DB_PATH)
    return _store
```

**Analysis:** ⚠️ **Potential Race Condition**
- If two coroutines check `if _store is None` simultaneously, both could create instances
- However, in single-threaded async, context switches only happen at await points
- The check and assignment are atomic (no await in between)

**Verdict:** Low risk in practice, but should use `asyncio.Lock` for correctness.

### 3. Intent Cache Access

**Scenario:** Multiple requests read/write to intent cache simultaneously

```python
# Current implementation in router.py
class IntentCache:
    def get(self, key: str) -> list | None:
        if key in self._cache:  # Read operation
            # No await points - safe in single-threaded async
            return self._cache[key][0] if time.time() < expiry else None
    
    def set(self, key: str, value: list) -> None:
        self._cache[key] = (value, expiry)  # Write operation
        # No await points - safe
```

**Analysis:** ✅ **No Race Condition**
- Dictionary operations are atomic in Python (CPython GIL)
- No await points during critical sections
- Single-threaded async provides natural serialization

**Verdict:** Current implementation is safe. No locking needed.

### 4. Database Write Operations

**Scenario:** Multiple requests writing to SQLite simultaneously

```python
# Current implementation uses aiosqlite
async def create_result(self, ...) -> str:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("INSERT INTO results ...")  # Write operation
        await db.commit()
```

**Analysis:** ✅ **Safe with WAL Mode**
- SQLite in WAL mode allows concurrent readers during writes
- Each connection gets its own transaction
- aiosqlite properly manages connection lifecycle

**Verdict:** Current implementation is safe. WAL mode provides necessary concurrency.

## Thread-Safety Strategy

### 1. Global Singleton Protection

**Approach:** Use `asyncio.Lock` for lazy initialization

```python
# Enhanced singleton pattern
_store: SessionStore | None = None
_store_lock = asyncio.Lock()

async def get_store(db_path: Path | None = None) -> SessionStore:
    global _store
    if _store is None:
        async with _store_lock:
            # Double-check after acquiring lock
            if _store is None:
                _store = SessionStore(db_path or DEFAULT_DB_PATH)
    return _store
```

**Why asyncio.Lock?**
- Designed specifically for async coroutines
- Non-blocking for other coroutines (yields at acquire)
- Prevents race conditions in lazy initialization

**Implementation Plan:**
- Apply to: `get_store()`, `get_router()`, `get_escalate_handler()`, `get_degraded_state_handler()`
- Each module gets its own lock to avoid contention
- Minimal performance impact (only used during first initialization)

### 2. First-Failure State Management

**Approach:** No locking needed - rely on async isolation

```python
# Current implementation is already safe
# Each fetch source tracks its own failure state
async def execute_with_timeout(source, required, timeout, task):
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        return source, required, result
    except asyncio.TimeoutError:
        # Isolated failure tracking - no shared state
        return source, required, SourceResult(status="timeout", ...)
```

**Why No Locking?**
- Each fetch source is an isolated coroutine
- No shared mutable state between sources
- `asyncio.gather()` provides natural isolation

### 3. Database Connection Management

**Approach:** Use aiosqlite connection-per-request pattern

```python
# Current implementation is correct
async def create_result(self, ...) -> str:
    # Each request gets its own connection
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("INSERT INTO results ...")
        await db.commit()
```

**Why Connection-per-Request?**
- WAL mode handles concurrent readers/writers
- No connection pool needed (WAL scales well)
- Simple and reliable

**Optimization Opportunity:**
- Consider connection pooling for high-load scenarios
- Use `aiosqlite.SQLitePool` for better performance under load
- Not needed for current expected load levels

### 4. Cache Access Patterns

**Approach:** Current implementation is safe - no changes needed

```python
# Current implementation already safe for single-threaded async
class IntentCache:
    def get(self, key: str) -> list | None:
        if key in self._cache:  # Atomic dict operation
            intent_mapping, expiry_timestamp = self._cache[key]
            if time.time() < expiry_timestamp:
                return intent_mapping
        return None
```

**Why No Locking?**
- Dictionary operations are atomic in CPython (GIL)
- No await points during critical sections
- Single-threaded async provides natural serialization

## Performance Considerations

### Locking Overhead

| Lock Type | Cost | When Used |
|-----------|------|-----------|
| `asyncio.Lock` | ~1-2 μs | Singleton initialization only |
| No locks | 0 μs | Normal operation (99.9% of cases) |

**Impact:** Negligible - locks only used during cold starts

### Alternative Approaches Considered

#### 1. Module-Level Locking (Rejected)
```python
# ❌ Not needed - too coarse-grained
_global_lock = asyncio.Lock()

async def any_operation():
    async with _global_lock:  # Unnecessary contention
        return await do_work()
```

**Why Rejected:** 
- Unnecessary performance overhead
- Blocks all operations instead of just critical sections
- Single-threaded async doesn't need global locking

#### 2. Atomic Operations (Rejected)
```python
# ❌ Not suitable for Python async
from threading import Thread
# ❌ Wrong approach - threading doesn't apply to async
```

**Why Rejected:**
- FastAPI uses async/await, not threading
- Threading primitives don't work with coroutines
- GIL already protects Python object access

#### 3. Database Transactions (Not Applicable)
```python
# SQLite handles this internally
# WAL mode provides necessary concurrency
```

**Why Not Applicable:**
- Database operations are already isolated via transactions
- WAL mode provides necessary concurrency guarantees

## Implementation Plan

### Phase 1: Protect Global Singletons (Priority: High)

**Files to Modify:**
- `src/session/store.py` - Protect `get_store()`
- `src/intent/router.py` - Protect `get_router()`
- `src/escalate/handler.py` - Protect `get_escalate_handler()`
- `src/errors/degraded_state.py` - Protect `get_degraded_state_handler()`

**Implementation Pattern:**
```python
# Add at module level
_lock = asyncio.Lock()
_instance = None

async def get_instance() -> SomeClass:
    global _instance
    if _instance is None:
        async with _lock:
            if _instance is None:
                _instance = SomeClass()
    return _instance
```

**Testing:**
- Simulate concurrent cold starts
- Verify only one instance is created
- Test with high concurrent request load

### Phase 2: Document Current Safety (Priority: Medium)

**Files to Create:**
- `docs/notes/thread-safety-analysis.md` - This document
- Update CLAUDE.md with concurrency notes

**Documentation Goals:**
- Explain why locking is minimal
- Guide future developers on concurrency patterns
- Document safe/unsafe patterns

### Phase 3: Add Monitoring (Priority: Low)

**Metrics to Track:**
- Singleton initialization count (should be 1 per module)
- Cache hit/miss rates (already implemented)
- Database lock contention (monitor WAL checkpoint performance)

## Monitoring and Validation

### Testing Strategy

```python
# Test concurrent singleton initialization
async def test_concurrent_singleton_initialization():
    tasks = [get_store() for _ in range(100)]
    results = await asyncio.gather(*tasks)
    
    # Verify all results are the same instance
    assert all(id(r) == id(results[0]) for r in results)
    
    # Verify initialization happened exactly once
    assert initialization_count == 1

# Test concurrent cache access
async def test_concurrent_cache_access():
    cache = IntentCache()
    
    # Concurrent reads and writes
    tasks = [
        cache.set(f"key{i}", f"value{i}"),
        cache.get(f"key{i}")
        for i in range(100)
    ]
    
    await asyncio.gather(*tasks)
    
    # Verify no data corruption
    assert len(cache.get_stats()) == 100
```

### Runtime Monitoring

```python
# Add to main.py startup
logger.info(f"Initialized with concurrency model: single-threaded async")
logger.info(f"Singletons: store={id(get_store())}, router={id(get_router())}")
```

## Conclusion

**Thread-Safety Approach:** Minimal Locking with Asyncio Primitives

**Key Decisions:**
1. **No locking needed** for most operations (cache, fetch, database)
2. **Use `asyncio.Lock`** for global singleton initialization only
3. **Rely on WAL mode** for database concurrency
4. **Leverage async isolation** for concurrent operations

**Performance Impact:** Negligible (~1-2 μs per cold start)

**Risk Level:** Low - current implementation is mostly safe; changes are defensive

**Implementation Priority:** 
- High: Protect global singletons (defensive)
- Medium: Document concurrency model
- Low: Add monitoring

---

## References

- **FastAPI Concurrency:** https://fastapi.tiangolo.com/async/
- **Asyncio Locks:** https://docs.python.org/3/library/asyncio-sync.html
- **SQLite WAL Mode:** https://www.sqlite.org/wal.html
- **CPython GIL:** https://wiki.python.org/moin/GlobalInterpreterLock

---

*Document Version: 1.0*
*Author: Thread-Safety Analysis for aide-de-camp*
*Date: 2026-08-06*
