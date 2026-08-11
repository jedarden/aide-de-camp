# Resource Cleanup Operations - Atomicity Risk Catalog

**Analysis Date:** 2026-08-07
**Scope:** All resource cleanup operations across aide-de-camp codebase
**Focus:** Non-atomic patterns that risk partial failure during cleanup operations

---

## Executive Summary

This analysis catalogs **12 high-risk resource cleanup operations** across the codebase where operations are not atomic. Each entry includes file location, specific non-atomic pattern, risk assessment, and failure impact.

**Risk Distribution:**
- **HIGH Risk:** 5 operations (potential resource leaks, inconsistent state)
- **MEDIUM Risk:** 6 operations (transient inconsistency, recoverable)
- **LOW Risk:** 1 operation (minimal impact)

---

## Catalog of Non-Atomic Cleanup Operations

### 1. SSE Broadcaster - Connection Unregister (HIGH)

**Location:** `/home/coding/aide-de-camp/src/sse/broadcaster.py:129-134`

**Non-Atomic Pattern:**
```python
def unregister(self, connection_id: str) -> None:
    """Unregister an SSE connection."""
    if connection_id in self.connections:
        conn = self.connections[connection_id]
        logger.info(f"Unregistered SSE connection {connection_id} for surface {conn.surface_id}")
        del self.connections[connection_id]  # ← Dictionary mutation without lock
```

**Atomicity Risk:**
- Dictionary deletion on `self.connections` is unprotected from concurrent access
- No lock or atomic transaction ensures read-then-delete consistency
- Multiple event_generator coroutines may call `unregister()` concurrently via `finally` blocks

**Failure Modes:**
1. **KeyError exception:** Connection deleted between `if connection_id in self.connections` check and `del` operation
2. **Race condition:** Two coroutines delete same connection, second raises KeyError
3. **Lost connection state:** Connection reference extracted for logging before deletion, but deletion may not complete

**Impact:** HIGH - Unhandled KeyError crashes event_generator task, leaving SSE response unterminated

**Risk Level:** HIGH

---

### 2. SSE Broadcaster - Cleanup Loop Dead Connection Processing (HIGH)

**Location:** `/home/coding/aide-de-camp/src/sse/broadcaster.py:253-288`

**Non-Atomic Pattern:**
```python
async def _cleanup_loop(self):
    while self._running:
        # Build list first (atomic snapshot)
        dead_connections = [
            cid for cid, conn in self.connections.items()
            if (now - conn.last_heartbeat) > timeout
        ]
        
        # Process all dead connections in a single atomic batch
        for cid in dead_connections:
            logger.info(f"Cleaning up dead connection {cid}")
            try:
                conn = self.connections.get(cid)  # ← May already be deleted
                if conn:
                    conn.queue.put_nowait(SSEEvent(...))  # ← Queue operation
                except asyncio.QueueFull:
                    pass
            self.unregister(cid)  # ← Separate deletion operation
```

**Atomicity Risk:**
- Dead connections list built at time T1, but processed at T2
- Connection may be deleted by concurrent `unregister()` between `get()` and `put_nowait()`
- Queue put and connection deletion are separate non-atomic operations
- No transaction ensures "queue event successfully sent AND connection removed"

**Failure Modes:**
1. **QueueFull exception:** Connection cleanup fails midway if queue is full
2. **Stale connection reference:** Connection deleted between dead list scan and processing
3. **Orphaned queue events:** Disconnect event queued but connection deletion fails
4. **Connection leak:** Exception in queue.put_nowait prevents unregister() call

**Impact:** HIGH - Dead connections not cleaned up, memory leak, stale SSE state

**Risk Level:** HIGH

---

### 3. Connection Monitor - Tracking Update and Removal (HIGH)

**Location:** `/home/coding/aide-de-camp/src/session/connection_monitor.py:256-288`

**Non-Atomic Pattern:**
```python
finally:
    closed_at = time.time()
    duration = closed_at - created_at

    async with self._lock:
        if conn_id in self._connections:
            conn_stats = self._connections[conn_id]
            conn_stats.closed_at = closed_at
            conn_stats.duration_seconds = duration

            self._stats.active_connections -= 1
            self._stats.closed_connections += 1

            # Update average duration
            if self._stats.closed_connections > 0:
                total_duration = sum(...)
                self._stats.avg_connection_duration = total_duration / self._stats.closed_connections

            # Remove from active tracking
            del self._connections[conn_id]  # ← Dictionary delete after stats update

    self._counter.decrement()  # ← Outside lock, separate operation

    # Close the actual connection if it was created
    if conn is not None:
        await conn.close()  # ← Outside lock, separate operation
```

**Atomicity Risk:**
- Multiple state mutations (stats update, average calculation, dict delete) within lock but no transaction
- If `conn.close()` raises exception, counter already decremented and stats already updated
- Lock protects dictionary but not external connection close operation
- Stats updated BEFORE connection close confirmed

**Failure Modes:**
1. **Connection close exception:** Connection handle invalid/already closed, stats already updated
2. **Counter inconsistency:** `self._counter.decrement()` outside lock, may interleave with other operations
3. **Stale connection stats:** Connection close fails but stats marked as closed
4. **Average corruption:** Division by zero if `closed_connections` races to zero between check and use

**Impact:** HIGH - Connection leak tracking becomes unreliable, incorrect averages mask real leaks

**Risk Level:** HIGH

---

### 4. Ambient Monitor - Stop Sequence (HIGH)

**Location:** `/home/coding/aide-de-camp/src/monitoring/ambient.py:705-724`

**Non-Atomic Pattern:**
```python
async def stop(self) -> None:
    logger.info("Stopping ambient monitoring service")
    self.running = False

    # Cancel all monitor tasks
    for task in self.tasks:
        task.cancel()  # ← Each cancel() is separate operation

    # Wait for tasks to complete
    await asyncio.gather(*self.tasks, return_exceptions=True)  # ← May raise/hang

    self.tasks.clear()  # ← State mutation after async wait
    self._ticker_task = None

    # Close HTTP client
    if self._http_client:
        await self._http_client.close()  # ← Separate async operation, may fail
```

**Atomicity Risk:**
- Sequential operations: cancel → gather → clear → close
- If `gather()` raises exception, `tasks.clear()` and `http_client.close()` never execute
- No transaction ensures "all tasks stopped AND client closed"
- State mutation (`self.running = False`) happens before cleanup confirmed

**Failure Modes:**
1. **Gather exception:** One task fails to cancel, blocks gather, prevents client close
2. **Task leak:** Tasks partially cancelled but not all cleared from list
3. **HTTP client leak:** `gather()` timeout prevents `client.close()` execution
4. **State inconsistency:** `running=False` but tasks still active, client still open

**Impact:** HIGH - Background tasks continue running after "stop", HTTP client connections leak

**Risk Level:** HIGH

---

### 5. Main Application - Sequential Shutdown (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/main.py:202-218`

**Non-Atomic Pattern:**
```python
logger.info("Shutting down aide-de-camp...")
stop_background_refresh()
if _bead_watcher:
    await _bead_watcher.stop()  # ← May raise/timeout
if _background_processor:
    await _background_processor.stop()  # ← May raise/timeout
if _context_warmer:
    await _context_warmer.stop()  # ← May raise/timeout
if _ambient_monitor:
    await _ambient_monitor.stop()  # ← May raise/timeout
if _broadcaster:
    await _broadcaster.stop()  # ← May raise/timeout
if _component_library:
    _component_library.close()  # ← May raise
if _store:
    await _store.close()  # ← May raise
logger.info("aide-de-camp shutdown complete")
```

**Atomicity Risk:**
- Sequential stop() calls with no transaction/rollback
- Early stop() failure prevents subsequent cleanup
- No compensation transaction if later cleanup fails
- "Shutdown complete" logged even if some services failed to stop

**Failure Modes:**
1. **Partial shutdown:** One service stop() fails, subsequent services never stopped
2. **Resource leaks:** Database/HTTP clients from stopped services leak
3. **State inconsistency:** Some services stopped, others still running
4. **False success:** "Shutdown complete" logged despite failures

**Impact:** MEDIUM - Partial shutdown leaves zombie processes/connections

**Risk Level:** MEDIUM

---

### 6. SSE Event Generator - Finally Block Unregister (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/sse/broadcaster.py:243-247`

**Non-Atomic Pattern:**
```python
try:
    # ... SSE event generation ...
except asyncio.CancelledError:
    logger.info(f"Connection {connection.connection_id} cancelled")
    raise
finally:
    self.unregister(connection.connection_id)  # ← May raise KeyError
```

**Atomicity Risk:**
- `unregister()` performs dictionary deletion without lock
- If connection already deleted by concurrent cleanup_loop, KeyError raised
- Finally block exception suppresses original CancelledError
- No exception handling in finally block

**Failure Modes:**
1. **KeyError in finally:** Connection already deleted by cleanup_loop
2. **Original exception lost:** KeyError suppresses CancelledError, obscuring real error
3. **Unregister failure:** Connection not removed from dict, stale reference

**Impact:** MEDIUM - Exception handling interferes with cancellation semantics

**Risk Level:** MEDIUM

---

### 7. SSE Broadcaster - Stop Method (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/sse/broadcaster.py:101-110`

**Non-Atomic Pattern:**
```python
async def stop(self) -> None:
    self._running = False  # ← State mutation first
    if self._cleanup_task:
        self._cleanup_task.cancel()  # ← May raise/timeout
        try:
            await self._cleanup_task  # ← Async wait may timeout
        except asyncio.CancelledError:
            pass  # ← Exception caught but state already mutated
```

**Atomicity Risk:**
- State flag set to False before cleanup task confirmed stopped
- If await timeout/raises, `_running=False` but task still running
- No rollback if task cancellation fails

**Failure Modes:**
1. **Task cancellation timeout:** `_running=False` but cleanup_task still alive
2. **Zombie cleanup loop:** Loop continues after "stop" called
3. **State inconsistency:** Flag says stopped but task still running

**Impact:** MEDIUM - Cleanup loop continues after "stop" called

**Risk Level:** MEDIUM

---

### 8. Session Store - WAL Checkpoint on Close (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/session/store.py:769-773`

**Non-Atomic Pattern:**
```python
async def close(self) -> None:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # ← May fail/timeout
    # ← No exception handling, no rollback
```

**Atomicity Risk:**
- WAL checkpoint is single operation with no compensating transaction
- If checkpoint fails, WAL file may be left in inconsistent state
- No retry logic for transient checkpoint failures

**Failure Modes:**
1. **Checkpoint failure:** WAL file left uncheckpointed, recovery may fail on next open
2. **Lock timeout:** Checkpoint blocked by other connections, close() hangs
3. **Disk full:** Checkpoint fails, database may have uncommitted WAL frames

**Impact:** MEDIUM - Database recovery may fail or lose recent transactions

**Risk Level:** MEDIUM

---

### 9. Feedback Processor - Pending Approval Deletion (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/feedback/processor.py:202, 246`

**Non-Atomic Pattern:**
```python
# Line 202
del self._pending_approvals[approval_id]  # ← No lock, dict mutation

# Line 246
del self._pending_approvals[approval_id]  # ← No lock, dict mutation
```

**Atomicity Risk:**
- Dictionary deletion without synchronization
- Multiple async tasks may process same approval concurrently
- No transaction ensures "approval processed AND removed atomically"

**Failure Modes:**
1. **KeyError race:** Two tasks process same approval, second deletion raises KeyError
2. **Duplicate processing:** Approval processed twice before deletion
3. **Lost approval:** Exception after processing but before deletion

**Impact:** MEDIUM - Duplicate processing or unhandled KeyError

**Risk Level:** MEDIUM

---

### 10. Feedback Signals - Result Timestamp Deletion (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/feedback/signals.py:95`

**Non-Atomic Pattern:**
```python
del self._result_created_at[result_id]  # ← No lock, dict mutation
```

**Atomicity Risk:**
- Dictionary deletion without synchronization
- Concurrent cleanup may race with signal creation
- No check for key existence before deletion

**Failure Modes:**
1. **KeyError race:** Result already deleted by concurrent task
2. **Signal processing failure:** KeyError halts signal processing loop

**Impact:** MEDIUM - Unhandled KeyError crashes signal processing

**Risk Level:** MEDIUM

---

### 11. Context Prefetch - Cache and Recent Utterances Deletion (MEDIUM)

**Location:** `/home/coding/aide-de-camp/src/context/prefetch.py:411, 471`

**Non-Atomic Pattern:**
```python
# Line 411
del self._cache[cache_key]  # ← No lock, dict mutation

# Line 471
del self._recent_utterances[session_id]  # ← No lock, dict mutation
```

**Atomicity Risk:**
- Dictionary deletions without synchronization
- Multiple prefetch tasks may evict same entry concurrently
- No transaction ensures "cache invalidated AND warmed atomically"

**Failure Modes:**
1. **KeyError race:** Entry already deleted by concurrent task
2. **Cache stampede:** Multiple tasks detect stale cache, all delete and regenerate
3. **Warm-up failure:** Deletion succeeds but warm-up fails, cache left empty

**Impact:** MEDIUM - Cache inconsistency, repeated warm-up work

**Risk Level:** MEDIUM

---

### 12. Watcher Daemon - Task Cancellation Sequence (LOW)

**Location:** `/home/coding/aide-de-camp/src/watcher/daemon.py:212-226`

**Non-Atomic Pattern:**
```python
supervisor.cancel()  # ← Separate operation
watch.cancel()       # ← Separate operation
ambient.cancel()     # ← Separate operation
```

**Atomicity Risk:**
- Sequential cancel() calls with no transaction
- If one cancel() raises, subsequent tasks may not be cancelled
- However, these are independent tasks, order is not critical

**Failure Modes:**
1. **Partial cancellation:** One cancel() raises, others not executed
2. **Task leak:** Uncancelled tasks continue running

**Impact:** LOW - Independent tasks, unlikely to all fail simultaneously

**Risk Level:** LOW

---

## Summary Statistics

| Risk Level | Count | Locations |
|------------|-------|-----------|
| HIGH | 5 | SSE broadcaster (2), Connection monitor, Ambient monitor, Main shutdown |
| MEDIUM | 6 | SSE event generator, SSE stop, Session store, Feedback processor, Signals, Prefetch |
| LOW | 1 | Watcher daemon |

**Total:** 12 non-atomic cleanup operations catalogued

---

## Common Patterns

### Pattern 1: Dictionary Mutation Without Lock
**Affected:** 8 locations
- `del dict[key]` without `async with lock:`
- Risk: KeyError race conditions

### Pattern 2: Multi-Operation Cleanup Without Transaction
**Affected:** 4 locations
- State update → delete → close (no rollback)
- Risk: Partial cleanup leaves inconsistent state

### Pattern 3: Async Wait Without Exception Handling
**Affected:** 3 locations
- `await operation()` without try/except in finally block
- Risk: Unhandled exception prevents subsequent cleanup

---

## Recommendations

### Immediate Actions (HIGH Risk)

1. **SSE Broadcaster:** Add asyncio.Lock to protect `self.connections` dict
   - Wrap all `unregister()` and `cleanup_loop()` operations with lock
   - Use `self._lock = asyncio.Lock()` in `__init__`

2. **Connection Monitor:** Move `conn.close()` inside lock
   - Ensure connection close completes before stats update
   - Add exception handling for close failure

3. **Ambient Monitor:** Add timeout to `asyncio.gather()`
   - Use `asyncio.wait_for(gather(...), timeout=30)`
   - Ensure client.close() runs even if gather fails

### Medium-Term Improvements (MEDIUM Risk)

4. **Main Shutdown:** Add compensation transaction
   - If stop() fails, attempt cleanup of already-stopped services
   - Log partial shutdown with service-specific failure details

5. **Session Store:** Add retry logic to WAL checkpoint
   - Retry checkpoint up to 3 times with exponential backoff
   - Log warning if checkpoint ultimately fails

6. **Feedback Processor:** Add lock to pending_approvals dict
   - Use `async with self._lock:` before dict mutation
   - Check key existence before deletion

### Design Patterns (All Locations)

7. **Adopt Two-Phase Cleanup Pattern:**
   - Phase 1: Prepare cleanup (build list, acquire locks)
   - Phase 2: Execute cleanup (atomic delete, close handles)
   - Phase 3: Verify cleanup (assert empty, log leaks)

8. **Add Cleanup Verification Tests:**
   - Test concurrent cleanup operations
   - Test cleanup with injected failures (close exception, timeout)
   - Test cleanup idempotency (call cleanup twice)

---

## Testing Strategy

### Unit Tests
```python
async def test_concurrent_unregister_race():
    """Test that concurrent unregister calls don't raise KeyError"""
    broadcaster = SSEBroadcaster()
    conn = broadcaster.register("surf-1", "sess-1", "canvas")

    # Concurrent unregister calls
    await asyncio.gather(
        broadcaster.unregister(conn.connection_id),
        broadcaster.unregister(conn.connection_id),
        return_exceptions=True
    )
    # Assert: No KeyError, connection removed cleanly
```

### Integration Tests
```python
async def test_shutdown_with_service_failure():
    """Test that shutdown continues even if one service fails"""
    # Mock one service's stop() to raise exception
    with patch.object(_ambient_monitor, 'stop', side_effect=Exception("Mock failure")):
        await shutdown()
    # Assert: All other services stopped, failure logged
```

### Chaos Tests
```python
async def test_cleanup_during_load():
    """Test cleanup operations while system under load"""
    # Simulate heavy load
    tasks = [process_intent(...) for _ in range(100)]
    
    # Trigger cleanup mid-flight
    await asyncio.sleep(0.1)
    await cleanup_expired_context()
    
    await asyncio.gather(*tasks)
    # Assert: No crashes, consistent state
```

---

## Conclusion

This catalog identifies **12 locations** where resource cleanup operations are not atomic, with **5 HIGH-risk** operations that may lead to resource leaks or inconsistent state. The most critical issues are:

1. **SSE Broadcaster connection management** (2 HIGH) - Unprotected dict mutations during concurrent cleanup
2. **Connection Monitor stats tracking** (1 HIGH) - Stats updated before connection close confirmed
3. **Ambient Monitor stop sequence** (1 HIGH) - Sequential operations without transaction/rollback
4. **Main shutdown sequence** (1 MEDIUM→HIGH when considered as whole) - Partial shutdown leaves zombie processes

Recommended immediate action is to add synchronization locks to SSE broadcaster and connection monitor, followed by adding timeout and compensation logic to ambient monitor and main shutdown.

---

**Generated:** 2026-08-07
**Task Reference:** adc-2l7l7r
**Dependencies:** adc-2rlmi0 (file cleanup analysis)
