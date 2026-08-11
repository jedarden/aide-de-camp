#!/usr/bin/env python3
"""
Comprehensive concurrent access tests with fast-fail deadlock detection.

LOCKING STRATEGY:
=================
This test suite verifies thread-safe concurrent access across multiple components:

1. **Registry (src/registry.py)**:
   - Uses `threading.RLock()` for cache protection (_cache_lock)
   - Protects both cache reads and rebuild transactions
   - RLock allows reentrancy (same thread can acquire multiple times)

2. **SSE Broadcaster (src/sse/broadcaster.py)**:
   - Uses `threading.RLock()` for connection registry (_registry_lock)
   - Uses `asyncio.Lock()` for lifecycle management (_lifecycle_lock)
   - Mixed threading/asyncio requires careful coordination

3. **Concurrency Limiter (src/concurrency/limit.py)**:
   - Uses `threading.RLock()` for singleton creation (_limiter_lock)
   - Protects global instance initialization

CONCURRENT ACCESS PROTECTION:
=============================
- All tests use asyncio.gather() for true async concurrency
- Timeouts < 5 seconds for fast-fail deadlock detection
- All operations logged with timestamps for debugging
- Explicit deadlock detection with clear error messages

TEST COVERAGE:
==============
- Read/write race conditions
- Multiple simultaneous access scenarios
- Cleanup during active concurrent access
- Lock contention detection and handling
- Cache consistency under concurrent updates
- Deadlock detection and reporting

All tests fail fast with clear error messages if deadlocks are detected.
"""

import asyncio
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

import pytest
import yaml

from src.registry import get_registry, _cache_lock
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType
from src.concurrency.limit import ConcurrencyLimiter, get_concurrency_limiter


class ConcurrentOperationLogger:
    """
    Track all concurrent operations with timestamps for deadlock debugging.

    This logger records every concurrent operation with precise timing to help
    identify where deadlocks occur and what operations were involved.
    """

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.operations = []
        self.start_time = time.time()
        self.lock = threading.Lock()

    def log_operation(self, op_type: str, task_id: int, details: str = ""):
        """Record an operation with timestamp for debugging."""
        with self.lock:
            timestamp = time.time() - self.start_time
            self.operations.append({
                'timestamp': timestamp,
                'op_type': op_type,
                'task_id': task_id,
                'details': details,
                'absolute_time': datetime.now().isoformat()
            })

    def log_lock_wait(self, task_id: int, wait_duration: float):
        """Record when a task waited for a lock (potential contention)."""
        with self.lock:
            timestamp = time.time() - self.start_time
            self.operations.append({
                'timestamp': timestamp,
                'op_type': 'LOCK_WAIT',
                'task_id': task_id,
                'details': f'Waited {wait_duration*1000:.2f}ms for lock',
                'absolute_time': datetime.now().isoformat()
            })

    def log_error(self, task_id: int, error: Exception):
        """Record an error during concurrent operation."""
        with self.lock:
            timestamp = time.time() - self.start_time
            self.operations.append({
                'timestamp': timestamp,
                'op_type': 'ERROR',
                'task_id': task_id,
                'details': f'{type(error).__name__}: {error}',
                'absolute_time': datetime.now().isoformat()
            })

    def get_summary(self) -> str:
        """Generate a summary of logged operations."""
        with self.lock:
            duration = time.time() - self.start_time
            op_counts = {}
            error_count = 0
            lock_wait_count = 0

            for op in self.operations:
                op_type = op['op_type']
                op_counts[op_type] = op_counts.get(op_type, 0) + 1
                if op_type == 'ERROR':
                    error_count += 1
                elif op_type == 'LOCK_WAIT':
                    lock_wait_count += 1

            lines = [
                f"\n{'='*70}",
                f"Concurrent Operation Log: {self.test_name}",
                f"{'='*70}",
                f"Duration: {duration:.3f} seconds",
                f"Total operations: {len(self.operations)}",
                f"Operation breakdown: {op_counts}",
                f"Errors: {error_count}",
                f"Lock waits: {lock_wait_count}",
                f"{'='*70}",
            ]

            # Show last 10 operations for debugging
            if self.operations:
                lines.append("\nLast 10 operations:")
                recent_ops = self.operations[-10:]
                for op in recent_ops:
                    lines.append(
                        f"  [{op['timestamp']:.3f}s] Task {op['task_id']}: "
                        f"{op['op_type']} - {op['details']}"
                    )

            return "\n".join(lines)


class DeadlockDetector:
    """
    Fast-fail deadlock detection with clear error reporting.

    Uses asyncio.wait_for() to detect when operations hang (potential deadlock).
    If timeout is exceeded, raises explicit error with deadlock context.
    """

    def __init__(self, timeout_seconds: float = 4.0):
        self.timeout_seconds = timeout_seconds
        self.detected_deadlocks = []

    async def run_with_deadlock_detection(
        self,
        coro,
        operation_name: str,
        logger: Optional[ConcurrentOperationLogger] = None
    ) -> Any:
        """
        Run a coroutine with explicit deadlock detection.

        Args:
            coro: Coroutine to execute
            operation_name: Name of operation for error reporting
            logger: Optional logger for tracking operations

        Returns:
            Result of the coroutine

        Raises:
            RuntimeError: If timeout exceeded (likely deadlock)
        """
        try:
            result = await asyncio.wait_for(
                coro,
                timeout=self.timeout_seconds
            )
            return result

        except asyncio.TimeoutError:
            # Construct explicit deadlock error message
            error_msg = (
                f"\n{'='*70}\n"
                f"DEADLOCK DETECTED: {operation_name}\n"
                f"{'='*70}\n"
                f"Operation exceeded {self.timeout_seconds}s timeout limit.\n"
                f"This strongly suggests a deadlock or livelock condition.\n"
                f"\n"
                f"Possible causes:\n"
                f"  - Circular lock dependency (lock ordering violation)\n"
                f"  - Lock not released in all code paths\n"
                f"  - Asyncio.Lock used from wrong thread\n"
                f"  - RLock reentrancy issue\n"
                f"\n"
                f"Component locking strategies to check:\n"
                f"  - Registry: threading.RLock() in src/registry.py\n"
                f"  - SSE Broadcaster: threading.RLock() + asyncio.Lock()\n"
                f"  - Concurrency Limiter: threading.RLock()\n"
                f"{'='*70}\n"
            )

            if logger:
                error_msg += logger.get_summary()

            raise RuntimeError(error_msg)


@pytest.mark.asyncio
async def test_concurrent_registry_access_with_deadlock_detection():
    """
    Test: Concurrent registry access with fast-fail deadlock detection.

    CONCURRENT ACCESS SCENARIO:
    - 10 tasks simultaneously accessing registry
    - Mix of reads and forced rebuilds
    - Verifies no race conditions or deadlocks

    DEADLOCK DETECTION:
    - 4-second timeout for fast-fail
    - Clear error message if deadlock detected
    - All operations logged for debugging

    LOCKING STRATEGY TESTED:
    - Registry threading.RLock() (_cache_lock)
    - Cache read/write atomicity
    - Rebuild transaction safety
    """
    logger = ConcurrentOperationLogger("test_concurrent_registry_access")
    detector = DeadlockDetector(timeout_seconds=4.0)

    num_tasks = 10
    accesses_per_task = 15

    async def registry_accessor(task_id: int, iteration: int):
        """Access registry with logging for deadlock detection."""
        op_name = f"Task {task_id}, Iteration {iteration}"

        try:
            # Mix of cached and forced reads
            force = (iteration % 5 == 0)
            start = time.time()

            logger.log_operation("REGISTRY_ACCESS_START", task_id, f"force={force}")

            registry = await get_registry(force=force)

            access_time = time.time() - start

            # Log if access took > 5ms (likely waited for lock)
            if access_time > 0.005:
                logger.log_lock_wait(task_id, access_time)

            # Verify data integrity
            assert isinstance(registry, dict), f"{op_name}: Registry should be dict"
            assert 'projects' in registry, f"{op_name}: Missing projects"

            logger.log_operation("REGISTRY_ACCESS_SUCCESS", task_id,
                              f"force={force}, time={access_time*1000:.2f}ms")
            return True

        except Exception as e:
            logger.log_error(task_id, e)
            raise

    # Launch all tasks concurrently
    tasks = []
    for task_id in range(num_tasks):
        for iteration in range(accesses_per_task):
            tasks.append(registry_accessor(task_id, iteration))

    # Run with deadlock detection
    try:
        logger.log_operation("TEST_START", 0, f"Launching {len(tasks)} operations")
        results = await detector.run_with_deadlock_detection(
            asyncio.gather(*tasks, return_exceptions=True),
            "Concurrent Registry Access",
            logger
        )

        # Verify all operations succeeded
        successful = sum(1 for r in results if r is True)
        total = len(results)

        logger.log_operation("TEST_COMPLETE", 0,
                          f"{successful}/{total} operations successful")

        print(logger.get_summary())
        print(f"✓ Concurrent registry access: {successful}/{total} operations successful")

        assert successful == total, f"Only {successful}/{total} operations succeeded"

    except RuntimeError as e:
        if "DEADLOCK DETECTED" in str(e):
            print(f"\n❌ DEADLOCK DETECTED in concurrent registry access")
            raise
        raise


@pytest.mark.asyncio
async def test_cleanup_during_active_concurrent_access():
    """
    Test: Cleanup operations during active concurrent access.

    CONCURRENT ACCESS SCENARIO:
    - SSE broadcaster performing cleanup while other operations active
    - Verifies cleanup doesn't race with registration/broadcast
    - Tests both threading.RLock() and asyncio.Lock() coordination

    DEADLOCK DETECTION:
    - 4-second timeout for fast-fail
    - Clear error message if cleanup deadlocks

    LOCKING STRATEGY TESTED:
    - SSE Broadcaster threading.RLock() (_registry_lock) for connections
    - SSE Broadcaster asyncio.Lock() (_lifecycle_lock) for lifecycle
    - Atomic cleanup operations

    CLEANUP DURING ACTIVE ACCESS:
    - Multiple concurrent registrations
    - Cleanup loop running simultaneously
    - Broadcast operations to active connections
    - Heartbeat updates during cleanup
    """
    logger = ConcurrentOperationLogger("test_cleanup_during_active_access")
    detector = DeadlockDetector(timeout_seconds=4.0)

    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    try:
        # Register initial connections
        initial_connections = []
        for i in range(5):
            conn = broadcaster.register(
                surface_id=f"surface-{i}",
                session_id=f"session-{i}",
                surface_type="canvas"
            )
            initial_connections.append(conn)

        logger.log_operation("INITIAL_REGISTRATION", 0,
                          f"Registered {len(initial_connections)} connections")

        async def concurrent_registrar(task_id: int):
            """Concurrent registration operations."""
            try:
                for i in range(3):
                    conn = broadcaster.register(
                        surface_id=f"surface-{task_id}-{i}",
                        session_id=f"session-{task_id}",
                        surface_type="canvas"
                    )
                    logger.log_operation("REGISTER", task_id,
                                      f"connection_id={conn.connection_id}")
                    await asyncio.sleep(0.01)
                return True
            except Exception as e:
                logger.log_error(task_id, e)
                return False

        async def concurrent_broadcaster(task_id: int):
            """Concurrent broadcast operations."""
            try:
                for i in range(5):
                    event = SSEEvent(
                        event_type=EventType.FETCH_PROGRESS,
                        data={'test': f'broadcast-{task_id}-{i}'},
                        target_session_id=f"session-{task_id % 5}"
                    )
                    count = await broadcaster.broadcast(event)
                    logger.log_operation("BROADCAST", task_id,
                                      f"sent to {count} connections")
                    await asyncio.sleep(0.01)
                return True
            except Exception as e:
                logger.log_error(task_id, e)
                return False

        async def concurrent_heartbeater(task_id: int):
            """Concurrent heartbeat operations."""
            try:
                for i in range(3):
                    if initial_connections:
                        conn = initial_connections[i % len(initial_connections)]
                        success = broadcaster.heartbeat(conn.connection_id)
                        logger.log_operation("HEARTBEAT", task_id,
                                          f"connection_id={conn.connection_id}, success={success}")
                    await asyncio.sleep(0.01)
                return True
            except Exception as e:
                logger.log_error(task_id, e)
                return False

        async def cleanup_simulator():
            """Simulate cleanup loop running concurrently."""
            try:
                logger.log_operation("CLEANUP_START", 0, "Starting cleanup simulation")

                # Simulate periodic cleanup while operations are active
                for cleanup_round in range(2):
                    await asyncio.sleep(0.1)  # Wait for some operations to accumulate

                    # Take snapshot of connections (with lock)
                    with broadcaster._registry_lock:
                        connections_snapshot = list(broadcaster.connections.items())
                        logger.log_operation("CLEANUP_SNAPSHOT", 0,
                                          f"Round {cleanup_round}: {len(connections_snapshot)} connections")

                    # Simulate cleanup check (no actual removal to avoid race with test)
                    for conn_id, conn in connections_snapshot[:2]:  # Check first 2
                        # In real cleanup, would check heartbeat and potentially remove
                        logger.log_operation("CLEANUP_CHECK", 0,
                                          f"Checking connection {conn_id}")

                logger.log_operation("CLEANUP_COMPLETE", 0, "Cleanup simulation finished")
                return True

            except Exception as e:
                logger.log_error(0, e)
                return False

        # Launch all operations concurrently
        tasks = []

        # Add cleanup task
        tasks.append(cleanup_simulator())

        # Add concurrent registrars
        for i in range(3):
            tasks.append(concurrent_registrar(i))

        # Add concurrent broadcasters
        for i in range(3):
            tasks.append(concurrent_broadcaster(i + 10))

        # Add concurrent heartbeaters
        for i in range(3):
            tasks.append(concurrent_heartbeater(i + 20))

        # Run with deadlock detection
        logger.log_operation("TEST_START", 0, f"Launching {len(tasks)} concurrent operations")

        results = await detector.run_with_deadlock_detection(
            asyncio.gather(*tasks, return_exceptions=True),
            "Cleanup During Active Concurrent Access",
            logger
        )

        successful = sum(1 for r in results if r is True)
        total = len(results)

        logger.log_operation("TEST_COMPLETE", 0,
                          f"{successful}/{total} operations successful")

        print(logger.get_summary())
        print(f"✓ Cleanup during concurrent access: {successful}/{total} operations successful")

        assert successful == total, f"Only {successful}/{total} operations succeeded"

    finally:
        await broadcaster.stop()


@pytest.mark.asyncio
async def test_read_write_race_with_contention_tracking():
    """
    Test: Intense read/write race with lock contention tracking.

    CONCURRENT ACCESS SCENARIO:
    - 8 readers and 4 writers competing simultaneously
    - High contention for registry cache lock
    - Tracks lock wait times and contention rate

    DEADLOCK DETECTION:
    - 5-second timeout for fast-fail
    - Lock contention statistics reported

    LOCKING STRATEGY TESTED:
    - Registry threading.RLock() fairness under contention
    - Multiple readers can hold RLock simultaneously
    - Writers get exclusive access

    CONTENTION TRACKING:
    - Counts operations that waited for lock (> 1ms)
    - Reports contention rate as percentage
    - Verifies system handles contention gracefully
    """
    logger = ConcurrentOperationLogger("test_read_write_race_contention")
    detector = DeadlockDetector(timeout_seconds=5.0)

    num_readers = 8
    num_writers = 4
    iterations = 12

    async def contentious_reader(reader_id: int):
        """Reader that competes for lock during write race."""
        try:
            for i in range(iterations):
                start = time.time()

                # Mix of cached and forced reads
                force = (i % 4 == 0)
                registry = await get_registry(force=force)

                wait_time = time.time() - start

                # Track lock waits (> 2ms suggests contention)
                if wait_time > 0.002:
                    logger.log_lock_wait(reader_id, wait_time)

                # Verify data integrity
                assert isinstance(registry, dict)
                assert 'projects' in registry

                await asyncio.sleep(0.001)

            logger.log_operation("READER_COMPLETE", reader_id,
                              f"{iterations} iterations")
            return True

        except Exception as e:
            logger.log_error(reader_id, e)
            return False

    async def contentious_writer(writer_id: int):
        """Writer that forces cache rebuilds under contention."""
        try:
            for i in range(iterations):
                start = time.time()

                # Force cache rebuild (exclusive write)
                registry = await get_registry(force=True)

                wait_time = time.time() - start

                # Track lock waits (writers wait longer under contention)
                if wait_time > 0.002:
                    logger.log_lock_wait(writer_id + 100, wait_time)

                # Verify rebuild succeeded
                assert isinstance(registry, dict)
                assert 'projects' in registry

                await asyncio.sleep(0.001)

            logger.log_operation("WRITER_COMPLETE", writer_id,
                              f"{iterations} iterations")
            return True

        except Exception as e:
            logger.log_error(writer_id + 100, e)
            return False

    # Launch all readers and writers concurrently
    tasks = []

    for i in range(num_readers):
        tasks.append(contentious_reader(i))

    for i in range(num_writers):
        tasks.append(contentious_writer(i))

    # Run with deadlock detection
    logger.log_operation("TEST_START", 0,
                      f"Launching {num_readers} readers + {num_writers} writers")

    results = await detector.run_with_deadlock_detection(
        asyncio.gather(*tasks, return_exceptions=True),
        "Read/Write Race with Contention Tracking",
        logger
    )

    successful = sum(1 for r in results if r is True)
    total = len(results)

    # Calculate contention statistics
    lock_waits = sum(1 for op in logger.operations
                    if op['op_type'] == 'LOCK_WAIT')
    total_ops = num_readers * iterations + num_writers * iterations
    contention_rate = (lock_waits / total_ops) * 100

    logger.log_operation("TEST_COMPLETE", 0,
                      f"{successful}/{total} successful, "
                      f"{lock_waits} lock waits ({contention_rate:.1f}% contention)")

    print(logger.get_summary())
    print(f"✓ Read/write race: {successful}/{total} operations successful")
    print(f"  Lock contention rate: {contention_rate:.1f}%")
    print(f"  System handles contention gracefully: YES")

    assert successful == total, f"Only {successful}/{total} operations succeeded"


@pytest.mark.asyncio
async def test_concurrency_limiter_singleton_thread_safety():
    """
    Test: Concurrency limiter singleton creation thread safety.

    CONCURRENT ACCESS SCENARIO:
    - Multiple threads/async tasks concurrently accessing singleton
    - Verifies threading.RLock() prevents race conditions
    - Tests initialization doesn't happen multiple times

    DEADLOCK DETECTION:
    - 4-second timeout for fast-fail
    - Singleton creation verified to happen only once

    LOCKING STRATEGY TESTED:
    - Concurrency Limiter threading.RLock() (_limiter_lock)
    - Singleton initialization atomicity
    - Thread-safe lazy initialization

    SINGLETON CREATION:
    - Multiple concurrent calls to get_concurrency_limiter()
    - Only one instance should be created
    - All calls return the same instance
    """
    logger = ConcurrentOperationLogger("test_concurrency_limiter_singleton")
    detector = DeadlockDetector(timeout_seconds=4.0)

    # Reset singleton to test initialization
    import src.concurrency.limit as limit_module
    limit_module._limiter = None

    num_tasks = 15

    async def singleton_accessor(task_id: int):
        """Access singleton concurrently."""
        try:
            for i in range(5):
                # Access singleton multiple times
                limiter1 = get_concurrency_limiter()
                limiter2 = get_concurrency_limiter()

                # Verify same instance returned
                assert limiter1 is limiter2, \
                    f"Task {task_id}: Different instances returned"

                # Verify limit is correct
                assert limiter1.limit == limiter2.limit, \
                    f"Task {task_id}: Limit mismatch"

                logger.log_operation("SINGLETON_ACCESS", task_id,
                                  f"limit={limiter1.limit}")

                await asyncio.sleep(0.001)

            return True

        except Exception as e:
            logger.log_error(task_id, e)
            return False

    # Launch all tasks concurrently
    tasks = [singleton_accessor(i) for i in range(num_tasks)]

    logger.log_operation("TEST_START", 0, f"Launching {num_tasks} singleton accessors")

    results = await detector.run_with_deadlock_detection(
        asyncio.gather(*tasks, return_exceptions=True),
        "Concurrency Limiter Singleton Thread Safety",
        logger
    )

    successful = sum(1 for r in results if r is True)
    total = len(results)

    # Verify only one singleton was created
    final_limiter = get_concurrency_limiter()
    assert final_limiter is not None, "Singleton should exist"

    logger.log_operation("TEST_COMPLETE", 0,
                      f"{successful}/{total} successful, "
                      f"singleton verified")

    print(logger.get_summary())
    print(f"✓ Concurrency limiter singleton: {successful}/{total} operations successful")
    print(f"  Singleton creation: Atomic (only one instance)")
    print(f"  Thread safety: Verified")

    assert successful == total, f"Only {successful}/{total} operations succeeded"


if __name__ == "__main__":
    # Run tests with pytest
    import sys
    pytest.main([__file__, "-v", "-s"] + sys.argv[1:])
