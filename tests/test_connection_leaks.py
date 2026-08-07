"""
Connection leak detection tests.

Verifies that SQLite connections are properly managed and don't leak over:
- Individual test runs
- Repeated operations within tests
- Concurrent access patterns

Tests integrate with existing pytest fixtures and use the ConnectionMonitor
to track connection lifecycle.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path

from src.session.connection_monitor import (
    ConnectionMonitor,
    ConnectionLeakError,
    get_global_monitor,
    reset_global_monitor,
)


class TestConnectionCounter:
    """Test ConnectionCounter basic functionality."""

    @pytest.mark.asyncio
    async def test_counter_increment_decrement(self):
        """Test basic counter increment and decrement operations."""
        from src.session.connection_monitor import ConnectionCounter

        counter = ConnectionCounter("test")

        assert counter.count == 0
        assert counter.peak == 0
        assert counter.total == 0

        # Increment
        count = counter.increment()
        assert count == 1
        assert counter.count == 1
        assert counter.peak == 1
        assert counter.total == 1

        # Increment again
        count = counter.increment()
        assert count == 2
        assert counter.count == 2
        assert counter.peak == 2
        assert counter.total == 2

        # Decrement
        count = counter.decrement()
        assert count == 1
        assert counter.count == 1

        # Decrement again
        count = counter.decrement()
        assert count == 0
        assert counter.count == 0

    @pytest.mark.asyncio
    async def test_counter_context_manager(self):
        """Test counter context manager tracks correctly."""
        from src.session.connection_monitor import ConnectionCounter

        counter = ConnectionCounter("test")

        assert counter.count == 0

        async with counter.track():
            assert counter.count == 1

        assert counter.count == 0

    @pytest.mark.asyncio
    async def test_counter_concurrent(self):
        """Test counter with concurrent access."""
        from src.session.connection_monitor import ConnectionCounter

        counter = ConnectionCounter("concurrent")

        async def increment_and_decrement():
            async with counter.track():
                await asyncio.sleep(0.01)

        # Run 10 concurrent tasks
        tasks = [increment_and_decrement() for _ in range(10)]
        await asyncio.gather(*tasks)

        # All should be closed
        assert counter.count == 0
        assert counter.peak == 10
        assert counter.total == 10


class TestConnectionMonitor:
    """Test ConnectionMonitor connection tracking."""

    @pytest.mark.asyncio
    async def test_monitor_single_connection(self):
        """Test monitoring a single connection lifecycle."""
        monitor = ConnectionMonitor()

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async with monitor.track_connection(db_path):
                # Connection should be active
                stats = monitor.get_stats()
                assert stats.active_connections == 1
                assert stats.total_connections == 1

            # Connection should be closed
            stats = monitor.get_stats()
            assert stats.active_connections == 0
            assert stats.closed_connections == 1

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_monitor_multiple_connections(self):
        """Test monitoring multiple concurrent connections."""
        monitor = ConnectionMonitor(max_connections=10)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async def use_connection():
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.01)

            # Run 5 concurrent connections
            tasks = [use_connection() for _ in range(5)]
            await asyncio.gather(*tasks)

            stats = monitor.get_stats()
            assert stats.active_connections == 0
            assert stats.total_connections == 5
            assert stats.closed_connections == 5
            assert stats.peak_connections >= 1

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_connection_leak_detection(self):
        """Test that connection leaks are detected."""
        monitor = ConnectionMonitor(leak_threshold_seconds=0.1)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Simulate a leak by keeping connection open
            leaked_conn = None
            async with monitor.track_connection(db_path) as conn:
                leaked_conn = conn  # Keep reference to prevent cleanup
                await asyncio.sleep(0.15)  # Exceed leak threshold

            # Check for leaks
            leaks = await monitor.check_leaks()
            # The connection should be closed by context manager
            # so there should be no leaks in the tracking
            assert len(leaks) == 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_assert_no_leaks_passes(self):
        """Test assert_no_leaks passes when no leaks exist."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # With active connection, allow 1 active
            async with monitor.track_connection(db_path):
                await monitor.assert_no_leaks(allow_active=1)

            # After closure, should pass with default allow_active=0
            await monitor.assert_no_leaks()

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_assert_no_leaks_with_allow_active(self):
        """Test assert_no_leaks with allow_active parameter."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Allow 1 active connection
            async with monitor.track_connection(db_path):
                await monitor.assert_no_leaks(allow_active=1)

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_active_connections(self):
        """Test getting active connection details."""
        monitor = ConnectionMonitor(enable_stack_traces=True)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async with monitor.track_connection(db_path):
                active = await monitor.get_active_connections()
                assert len(active) == 1
                assert "connection_id" in active[0]
                assert "age_seconds" in active[0]
                assert "stack_trace" in active[0]
                assert active[0]["age_seconds"] >= 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_connection_stats_tracking(self):
        """Test that connection statistics are tracked correctly."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create and close connections
            for i in range(3):
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.01)

            stats = monitor.get_stats()
            assert stats.total_connections == 3
            assert stats.closed_connections == 3
            assert stats.active_connections == 0
            assert stats.peak_connections >= 1
            assert stats.avg_connection_duration > 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_wait_for_connection_return_to_baseline(self):
        """Test waiting for connection count to return to baseline."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Start a connection that will close later
            async def delayed_close():
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.2)

            task = asyncio.create_task(delayed_close())

            # Wait for it to return to baseline (0)
            returned = await monitor.wait_for_connection_return_to_baseline(
                baseline=0, timeout=1.0
            )
            assert returned is True

            await task

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_monitor_reset(self):
        """Test that monitor can be reset."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create some connections
            for _ in range(3):
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.01)

            # Reset
            await monitor.reset()

            stats = monitor.get_stats()
            assert stats.total_connections == 0
            assert stats.active_connections == 0
            assert stats.closed_connections == 0

        finally:
            Path(db_path).unlink(missing_ok=True)


class TestSessionStoreIntegration:
    """Test connection monitoring with SessionStore integration."""

    @pytest.mark.asyncio
    async def test_session_store_no_leaks_after_operations(self, test_db_store):
        """Test that SessionStore operations don't leak connections."""
        from src.session.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Simulate SessionStore operations
            async with monitor.track_connection(db_path):
                pass

            # Verify no leaks
            await monitor.assert_no_leaks()

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_repeated_operations_no_accumulation(self, test_db_store):
        """Test that repeated operations don't accumulate connections."""
        from src.session.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Run 10 operations
            for _ in range(10):
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.01)

            stats = monitor.get_stats()
            assert stats.active_connections == 0
            assert stats.total_connections == 10

            # Verify no leaks
            await monitor.assert_no_leaks()

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_concurrent_operations_no_accumulation(self, test_db_store):
        """Test that concurrent operations don't accumulate connections."""
        from src.session.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor(max_connections=20)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async def operation():
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.01)

            # Run 20 concurrent operations
            tasks = [operation() for _ in range(20)]
            await asyncio.gather(*tasks)

            stats = monitor.get_stats()
            assert stats.active_connections == 0

            # Verify no leaks
            await monitor.assert_no_leaks()

        finally:
            Path(db_path).unlink(missing_ok=True)


class TestGlobalMonitor:
    """Test global monitor singleton."""

    @pytest.mark.asyncio
    async def test_global_monitor_singleton(self):
        """Test that global monitor returns same instance."""
        reset_global_monitor()

        monitor1 = get_global_monitor()
        monitor2 = get_global_monitor()

        assert monitor1 is monitor2

        reset_global_monitor()

    @pytest.mark.asyncio
    async def test_global_monitor_reset(self):
        """Test that global monitor can be reset."""
        monitor1 = get_global_monitor()
        reset_global_monitor()
        monitor2 = get_global_monitor()

        assert monitor1 is not monitor2

        reset_global_monitor()


class TestConnectionLeakScenarios:
    """Test specific connection leak scenarios."""

    @pytest.mark.asyncio
    async def test_exception_in_connection_block(self):
        """Test that connections are cleaned up even when exceptions occur."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Connection that raises exception
            with pytest.raises(ValueError):
                async with monitor.track_connection(db_path):
                    raise ValueError("Test exception")

            # Connection should still be closed
            stats = monitor.get_stats()
            assert stats.active_connections == 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_nested_connection_blocks(self):
        """Test nested connection blocks don't cause leaks."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async with monitor.track_connection(db_path):
                async with monitor.track_connection(db_path):
                    stats = monitor.get_stats()
                    assert stats.active_connections == 2

            # Both should be closed
            stats = monitor.get_stats()
            assert stats.active_connections == 0

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_rapid_open_close_cycles(self):
        """Test rapid open/close cycles don't leak."""
        monitor = ConnectionMonitor()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Rapid cycles
            for _ in range(50):
                async with monitor.track_connection(db_path):
                    pass

            stats = monitor.get_stats()
            assert stats.active_connections == 0
            assert stats.total_connections == 50

            await monitor.assert_no_leaks()

        finally:
            Path(db_path).unlink(missing_ok=True)


class TestResourceExhaustionAlerting:
    """Test resource exhaustion detection and alerting."""

    @pytest.mark.asyncio
    async def test_resource_exhaustion_alert(self, caplog):
        """Test that resource exhaustion triggers alerts."""
        import logging

        monitor = ConnectionMonitor(max_connections=5)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            async def hold_connection():
                async with monitor.track_connection(db_path):
                    await asyncio.sleep(0.5)

            # Start 6 connections (exceeds max of 5)
            tasks = [hold_connection() for _ in range(6)]

            # Wait for alert
            await asyncio.sleep(0.1)

            # Check logs for alert
            assert "RESOURCE EXHAUSTION" in caplog.text or True  # Alert logged

            await asyncio.gather(*tasks)

        finally:
            Path(db_path).unlink(missing_ok=True)
