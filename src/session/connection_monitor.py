"""
SQLite connection leak detection and monitoring.

Tracks aiosqlite connection lifecycle to detect connection leaks and resource
exhaustion patterns during testing and production.

Provides:
- ConnectionCounter: Tracks active connection count with thread-safety
- ConnectionMonitor: Monitors connection lifecycle for leaks
- ConnectionLeakError: Raised when connection leaks are detected
"""

import asyncio
import logging
import threading
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from collections import deque

import aiosqlite

logger = logging.getLogger(__name__)


class ConnectionLeakError(RuntimeError):
    """Raised when connection leaks are detected."""
    pass


@dataclass
class ConnectionStats:
    """Statistics for a single connection."""
    created_at: float
    closed_at: Optional[float] = None
    stack_trace: str = ""
    duration_seconds: float = 0.0


@dataclass
class MonitorStats:
    """Aggregate monitoring statistics."""
    total_connections: int = 0
    active_connections: int = 0
    closed_connections: int = 0
    leaked_connections: int = 0
    peak_connections: int = 0
    avg_connection_duration: float = 0.0
    last_activity: float = field(default_factory=time.time)


class ConnectionCounter:
    """
    Thread-safe counter for tracking active SQLite connections.

    Uses atomic operations and locks to ensure accurate counts across
    concurrent access patterns in async/await code.

    Example:
        counter = ConnectionCounter()
        async with counter.track():
            # Connection is active
            pass
        # Connection is automatically decremented
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._count = 0
        self._lock = threading.Lock()
        self._peak = 0
        self._total = 0

    @property
    def count(self) -> int:
        """Get current connection count."""
        with self._lock:
            return self._count

    @property
    def peak(self) -> int:
        """Get peak connection count."""
        with self._lock:
            return self._peak

    @property
    def total(self) -> int:
        """Get total connections created."""
        with self._lock:
            return self._total

    def increment(self) -> int:
        """Increment connection count and return new value."""
        with self._lock:
            self._count += 1
            self._total += 1
            self._peak = max(self._peak, self._count)
            return self._count

    def decrement(self) -> int:
        """Decrement connection count and return new value."""
        with self._lock:
            if self._count > 0:
                self._count -= 1
            else:
                logger.warning(
                    f"ConnectionCounter[{self.name}]: "
                    f"Attempted to decrement count below zero (count={self._count})"
                )
            return self._count

    def reset(self) -> None:
        """Reset counter to zero."""
        with self._lock:
            self._count = 0
            self._peak = 0
            self._total = 0

    @asynccontextmanager
    async def track(self):
        """Context manager that tracks a connection lifecycle."""
        self.increment()
        try:
            yield
        finally:
            self.decrement()


class ConnectionMonitor:
    """
    Monitor SQLite connection lifecycle for leaks and resource exhaustion.

    Tracks all connections created through its wrapper, recording:
    - Active connection count
    - Connection creation/closure timestamps
    - Stack traces of connection creation
    - Connection durations
    - Peak usage patterns

    Detects leaks by:
    - Monitoring connections that remain open beyond threshold
    - Checking for unclosed connections after test runs
    - Alerting on resource exhaustion patterns

    Example:
        monitor = ConnectionMonitor()

        # Wrap connection creation
        async with monitor.track_connection() as conn:
            await conn.execute("SELECT * FROM sessions")

        # Check for leaks after test
        monitor.assert_no_leaks()

        # Get statistics
        stats = monitor.get_stats()
        print(f"Active connections: {stats.active_connections}")
    """

    def __init__(
        self,
        leak_threshold_seconds: float = 10.0,
        max_connections: int = 100,
        enable_stack_traces: bool = True,
    ):
        """
        Initialize connection monitor.

        Args:
            leak_threshold_seconds: Duration beyond which an open connection is flagged as potential leak
            max_connections: Maximum connections before resource exhaustion is flagged
            enable_stack_traces: Whether to capture stack traces on connection creation
        """
        self.leak_threshold_seconds = leak_threshold_seconds
        self.max_connections = max_connections
        self.enable_stack_traces = enable_stack_traces

        # Connection tracking
        self._connections: dict[int, ConnectionStats] = {}
        self._connection_id = 0
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = MonitorStats()
        self._counter = ConnectionCounter("connection_monitor")

        # Activity tracking for resource exhaustion detection
        self._activity_history: deque = deque(maxlen=1000)
        self._exhaustion_alerted = False

        # Weakref cleanup of closed connections
        self._weak_refs: list[weakref.ref] = []

    def get_stats(self) -> MonitorStats:
        """Get current monitoring statistics."""
        return MonitorStats(
            total_connections=self._stats.total_connections,
            active_connections=self._stats.active_connections,
            closed_connections=self._stats.closed_connections,
            leaked_connections=self._stats.leaked_connections,
            peak_connections=self._stats.peak_connections,
            avg_connection_duration=self._stats.avg_connection_duration,
            last_activity=self._stats.last_activity,
        )

    @asynccontextmanager
    async def track_connection(self, db_path: str):
        """
        Context manager that wraps aiosqlite connection with monitoring.

        Yields a monitored aiosqlite connection that tracks its lifecycle
        and detects leaks if not properly closed.

        Args:
            db_path: Path to SQLite database file

        Yields:
            aiosqlite.Connection: Monitored database connection

        Raises:
            ConnectionLeakError: If connection leak is detected
        """
        conn_id = self._connection_id
        self._connection_id += 1

        # Record connection creation
        created_at = time.time()
        stack_trace = self._capture_stack() if self.enable_stack_traces else ""

        async with self._lock:
            self._connections[conn_id] = ConnectionStats(
                created_at=created_at,
                stack_trace=stack_trace,
            )
            self._stats.total_connections += 1
            self._stats.active_connections += 1
            self._stats.peak_connections = max(
                self._stats.peak_connections, self._stats.active_connections
            )

        # Check for resource exhaustion
        if self._stats.active_connections >= self.max_connections:
            self._alert_resource_exhaustion()

        self._counter.increment()
        conn = None

        try:
            # Create actual connection
            conn = await aiosqlite.connect(db_path)
            yield conn

        finally:
            # Record connection closure
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
                        total_duration = sum(
                            c.duration_seconds
                            for c in self._connections.values()
                            if c.closed_at is not None
                        )
                        self._stats.avg_connection_duration = (
                            total_duration / self._stats.closed_connections
                        )

                    # Remove from active tracking
                    del self._connections[conn_id]

            self._counter.decrement()

            # Close the actual connection if it was created
            if conn is not None:
                await conn.close()

    def _capture_stack(self) -> str:
        """Capture current stack trace for connection creation debugging."""
        import traceback

        return "\n".join(traceback.format_stack())

    def _alert_resource_exhaustion(self) -> None:
        """Alert on resource exhaustion pattern."""
        if self._exhaustion_alerted:
            return

        self._exhaustion_alerted = True

        logger.error(
            f"ConnectionMonitor: RESOURCE EXHAUSTION - "
            f"Active connections ({self._stats.active_connections}) "
            f"at or above max ({self.max_connections})"
        )

        # Log connection details
        for conn_id, stats in self._connections.items():
            logger.error(
                f"Connection {conn_id}: "
                f"age={time.time() - stats.created_at:.1f}s, "
                f"stack:\n{stats.stack_trace}"
            )

    async def check_leaks(self) -> list[tuple[int, ConnectionStats]]:
        """
        Check for connection leaks.

        Returns list of (conn_id, stats) tuples for connections that have been
        open longer than leak_threshold_seconds.

        Returns:
            List of leaked connection details
        """
        now = time.time()
        leaked = []

        async with self._lock:
            for conn_id, stats in self._connections.items():
                age = now - stats.created_at
                if age > self.leak_threshold_seconds:
                    leaked.append((conn_id, stats))

        return leaked

    async def assert_no_leaks(
        self, message: str = "Connection leak detected", allow_active: int = 0
    ) -> None:
        """
        Assert that no connection leaks exist.

        Args:
            message: Error message if leak is detected
            allow_active: Number of active connections to allow (for baseline tracking)

        Raises:
            ConnectionLeakError: If leaks are detected beyond allow_active threshold
        """
        leaked = await self.check_leaks()

        async with self._lock:
            active_count = self._stats.active_connections

        if len(leaked) > 0 or active_count > allow_active:
            leak_details = []
            for conn_id, stats in leaked:
                age = time.time() - stats.created_at
                leak_details.append(
                    f"Connection {conn_id}: age={age:.1f}s\nstack:\n{stats.stack_trace}"
                )

            raise ConnectionLeakError(
                f"{message}\n"
                f"Active connections: {active_count} (allowed: {allow_active})\n"
                f"Leaked connections: {len(leaked)}\n"
                f"\nLeak details:\n" + "\n\n".join(leak_details)
            )

    async def get_active_connections(self) -> list[dict]:
        """
        Get details of all currently active connections.

        Returns:
            List of connection details dictionaries
        """
        active = []

        async with self._lock:
            now = time.time()
            for conn_id, stats in self._connections.items():
                active.append(
                    {
                        "connection_id": conn_id,
                        "age_seconds": now - stats.created_at,
                        "stack_trace": stats.stack_trace,
                    }
                )

        return active

    async def reset(self) -> None:
        """Reset monitor state (for test isolation)."""
        async with self._lock:
            self._connections.clear()
            self._stats = MonitorStats()
            self._counter.reset()
            self._activity_history.clear()
            self._exhaustion_alerted = False

    def get_connection_count(self) -> int:
        """Get current active connection count (synchronous)."""
        return self._counter.count

    async def wait_for_connection_return_to_baseline(
        self,
        baseline: int,
        timeout: float = 5.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """
        Wait for connection count to return to baseline.

        Useful for tests that need to verify connection cleanup after operations.

        Args:
            baseline: Expected baseline connection count
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            True if count returned to baseline, False if timeout exceeded
        """
        start = time.time()

        while time.time() - start < timeout:
            count = self.get_connection_count()
            if count <= baseline:
                return True
            await asyncio.sleep(poll_interval)

        return False


# Global monitor instance (can be swapped for testing)
_global_monitor: Optional[ConnectionMonitor] = None


def get_global_monitor() -> ConnectionMonitor:
    """Get or create global connection monitor."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ConnectionMonitor()
    return _global_monitor


def reset_global_monitor() -> None:
    """Reset global monitor (for test isolation)."""
    global _global_monitor
    _global_monitor = None
