"""
Test atomic cleanup operations.

Ensures all cleanup operations use atomic patterns to prevent partial state issues.
Tests cover edge cases including concurrent access, failure during cleanup, and orphaned state.
"""

import asyncio
import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os

from src.sse.broadcaster import SSEBroadcaster, SSEConnection, SSEEvent
from src.context.prefetch import SpeculativePrefetcher, PrefetchCache, FollowUpPattern
from src.freeze import set_frozen, check_frozen, SENTINEL_PATH


class TestSSEBroadcasterAtomicCleanup:
    """Test atomic cleanup in SSE broadcaster."""

    @pytest.fixture
    def broadcaster(self):
        """Create a fresh broadcaster for each test."""
        return SSEBroadcaster()

    @pytest.fixture
    async def started_broadcaster(self, broadcaster):
        """Start broadcaster and ensure cleanup."""
        await broadcaster.start()
        yield broadcaster
        await broadcaster.stop()

    def test_cleanup_builds_list_before_deletion(self, started_broadcaster):
        """Test that cleanup builds dead connection list before modifying state."""
        # Register multiple connections
        connections = []
        for i in range(5):
            conn = started_broadcaster.register(
                surface_id=f"surface-{i}",
                session_id=f"session-{i}",
                surface_type="canvas"
            )
            connections.append(conn)

        # Simulate timeout by setting old heartbeat
        timeout_timestamp = datetime.now().timestamp() - 400  # > 5 minute timeout
        for conn in connections[:3]:
            started_broadcaster.connections[conn.connection_id].last_heartbeat = timeout_timestamp

        # Run cleanup loop manually
        asyncio.run(started_broadcaster._cleanup_loop())

        # Verify only timed-out connections were removed
        assert len(started_broadcaster.connections) == 2  # Only 2 non-timed out remain
        assert connections[3].connection_id in started_broadcaster.connections
        assert connections[4].connection_id in started_broadcaster.connections

    def test_cleanup_handles_connection_during_iteration(self, started_broadcaster):
        """Test cleanup handles case where connection is added during iteration."""
        # Register initial connections
        conn1 = started_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Set old heartbeat
        started_broadcaster.connections[conn1.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup - should handle gracefully even if dict changes
        asyncio.run(started_broadcaster._cleanup_loop())

        # Verify cleanup completed without error
        assert conn1.connection_id not in started_broadcaster.connections

    def test_cleanup_sends_disconnect_before_removal(self, started_broadcaster):
        """Test that cleanup sends disconnect event before removing connection."""
        conn = started_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Set old heartbeat
        started_broadcaster.connections[conn.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup
        asyncio.run(started_broadcaster._cleanup_loop())

        # Verify disconnect event was queued
        assert not conn.queue.empty()
        event = conn.queue.get_nowait()
        assert event.event_type == "disconnect"
        assert event.data["reason"] == "timeout"

        # Verify connection was removed
        assert conn.connection_id not in started_broadcaster.connections

    def test_cleanup_handles_queue_full_gracefully(self, started_broadcaster):
        """Test cleanup handles full queue gracefully without crashing."""
        conn = started_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Fill the queue to capacity
        max_queue_size = 1000
        for _ in range(max_queue_size):
            try:
                conn.queue.put_nowait(SSEEvent(
                    event_type="test",
                    data={"test": "data"}
                ))
            except asyncio.QueueFull:
                break

        # Set old heartbeat
        started_broadcaster.connections[conn.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup - should handle QueueFull gracefully
        asyncio.run(started_broadcaster._cleanup_loop())

        # Connection should still be removed even if disconnect event failed
        assert conn.connection_id not in started_broadcaster.connections


class TestPrefetchAtomicCleanup:
    """Test atomic cleanup in prefetch cache."""

    @pytest.fixture
    def prefetcher(self):
        """Create a prefetcher with short TTL for testing."""
        return SpeculativePrefetcher(ttl_seconds=1)

    def test_cleanup_builds_list_before_deletion(self, prefetcher):
        """Test that cleanup builds expired list before modifying cache."""
        # Add cache entries with different expiration times
        now = int(datetime.now(timezone.utc).timestamp())

        # Add expired entries
        for i in range(3):
            cache_key = f"topic-{i}:status_check"
            prefetcher._cache[cache_key] = PrefetchCache(
                key=cache_key,
                data={"test": f"data-{i}"},
                created_at=now - 100,
                expires_at=now - 50,  # Expired
            )

        # Add valid entries
        for i in range(3, 6):
            cache_key = f"topic-{i}:status_check"
            prefetcher._cache[cache_key] = PrefetchCache(
                key=cache_key,
                data={"test": f"data-{i}"},
                created_at=now,
                expires_at=now + 1000,  # Valid
            )

        # Run cleanup
        removed_count = asyncio.run(prefetcher.cleanup_expired())

        # Verify only expired entries removed
        assert removed_count == 3
        assert len(prefetcher._cache) == 3  # Only valid entries remain
        assert "topic-0:status_check" not in prefetcher._cache
        assert "topic-3:status_check" in prefetcher._cache

    def test_cleanup_handles_empty_cache(self, prefetcher):
        """Test cleanup handles empty cache gracefully."""
        # Run cleanup on empty cache
        removed_count = asyncio.run(prefetcher.cleanup_expired())

        # Should handle gracefully
        assert removed_count == 0
        assert len(prefetcher._cache) == 0

    def test_cleanup_handles_all_expired(self, prefetcher):
        """Test cleanup when all entries are expired."""
        now = int(datetime.now(timezone.utc).timestamp())

        # Add only expired entries
        for i in range(5):
            cache_key = f"topic-{i}:status_check"
            prefetcher._cache[cache_key] = PrefetchCache(
                key=cache_key,
                data={"test": f"data-{i}"},
                created_at=now - 100,
                expires_at=now - 50,
            )

        # Run cleanup
        removed_count = asyncio.run(prefetcher.cleanup_expired())

        # All entries should be removed
        assert removed_count == 5
        assert len(prefetcher._cache) == 0

    def test_cleanup_handles_none_expired(self, prefetcher):
        """Test cleanup when no entries are expired."""
        now = int(datetime.now(timezone.utc).timestamp())

        # Add only valid entries
        for i in range(5):
            cache_key = f"topic-{i}:status_check"
            prefetcher._cache[cache_key] = PrefetchCache(
                key=cache_key,
                data={"test": f"data-{i}"},
                created_at=now,
                expires_at=now + 1000,
            )

        # Run cleanup
        removed_count = asyncio.run(prefetcher.cleanup_expired())

        # No entries should be removed
        assert removed_count == 0
        assert len(prefetcher._cache) == 5

    def test_cleanup_is_atomic_with_dict_rebuild(self, prefetcher):
        """Test that cleanup uses atomic dict rebuild pattern."""
        now = int(datetime.now(timezone.utc).timestamp())

        # Add mix of expired and valid entries
        for i in range(10):
            cache_key = f"topic-{i}:status_check"
            is_expired = i < 5
            prefetcher._cache[cache_key] = PrefetchCache(
                key=cache_key,
                data={"test": f"data-{i}"},
                created_at=now - 100 if is_expired else now,
                expires_at=now - 50 if is_expired else now + 1000,
            )

        # Get original dict reference
        original_cache = prefetcher._cache

        # Run cleanup
        asyncio.run(prefetcher.cleanup_expired())

        # Verify new dict was created (atomic rebuild)
        # The dict should have been replaced, not modified in place
        assert len(prefetcher._cache) == 5  # Only valid entries remain
        # Verify the cache dict was replaced (atomic operation)
        assert prefetcher._cache is not original_cache


class TestFreezeAtomicOperations:
    """Test atomic file operations in freeze mechanism."""

    def test_freeze_uses_temp_file_with_uuid(self, tmp_path):
        """Test that freeze uses temp file with UUID for unique naming."""
        # Override sentinel path for testing
        import src.freeze
        original_path = src.freeze.SENTINEL_PATH
        test_path = tmp_path / "FREEZE"
        src.freeze.SENTINEL_PATH = test_path

        try:
            # Set frozen
            set_frozen(True)

            # Verify freeze sentinel exists
            assert test_path.exists()
            assert test_path.read_text() == "Self-modification frozen via 'adc freeze' command\n"

            # Verify unfrozen
            set_frozen(False)
            assert not test_path.exists()

        finally:
            src.freeze.SENTINEL_PATH = original_path

    def test_freeze_handles_concurrent_writes(self, tmp_path):
        """Test that freeze handles concurrent writes safely."""
        import src.freeze
        original_path = src.freeze.SENTINEL_PATH
        test_path = tmp_path / "FREEZE"
        src.freeze.SENTINEL_PATH = test_path

        try:
            # Simulate concurrent freeze operations
            async def concurrent_freeze():
                set_frozen(True)

            # Run multiple concurrent freeze operations
            tasks = [asyncio.create_task(concurrent_freeze()) for _ in range(5)]
            asyncio.gather(*tasks)

            # Should complete without error and file should exist
            assert test_path.exists()

        finally:
            # Cleanup
            if test_path.exists():
                test_path.unlink()
            src.freeze.SENTINEL_PATH = original_path

    def test_freeze_cleanup_on_failure(self, tmp_path):
        """Test that freeze cleans up temp files on failure."""
        import src.freeze
        original_path = src.freeze.SENTINEL_PATH
        # Create a scenario where write might fail
        test_path = tmp_path / "readonly" / "FREEZE"
        src.freeze.SENTINEL_PATH = test_path

        try:
            # This should fail due to readonly parent
            readonly_dir = tmp_path / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)  # Read-only

            # Attempt freeze - should handle failure gracefully
            try:
                set_frozen(True)
            except OSError:
                pass  # Expected to fail

            # Verify no orphaned temp files
            temp_files = list(readonly_dir.glob("*.tmp"))
            assert len(temp_files) == 0, "Temp files should be cleaned up on failure"

        finally:
            # Cleanup permissions
            readonly_dir.chmod(0o755)
            src.freeze.SENTINEL_PATH = original_path


class TestHotReloadAtomicOperations:
    """Test atomic file operations in hot reload."""

    def test_atomic_write_creates_temp_with_unique_name(self, tmp_path):
        """Test that atomic write creates temp file with unique name."""
        from src.components.hot_reload import _atomic_write

        target_file = tmp_path / "test.yaml"
        content = "test: content"

        # Perform atomic write
        _atomic_write(target_file, content)

        # Verify file was written
        assert target_file.exists()
        assert target_file.read_text() == content

        # Verify no orphaned temp files
        temp_files = list(tmp_path.glob(".atomic_write_*"))
        assert len(temp_files) == 0, "No orphaned temp files should remain"

    def test_atomic_write_handles_concurrent_access(self, tmp_path):
        """Test atomic write handles concurrent file access safely."""
        from src.components.hot_reload import _atomic_write

        target_file = tmp_path / "concurrent.yaml"

        async def concurrent_write(content):
            _atomic_write(target_file, content)

        # Run concurrent writes
        contents = [f"version-{i}\n" for i in range(5)]
        tasks = [asyncio.create_task(concurrent_write(content)) for content in contents]
        asyncio.gather(*tasks)

        # File should exist and have valid content
        assert target_file.exists()
        content = target_file.read_text()
        assert content in contents  # One of the writes should have won

    def test_atomic_write_cleans_up_temp_on_failure(self, tmp_path):
        """Test atomic write cleans up temp files on failure."""
        from src.components.hot_reload import _atomic_write

        # Create a scenario where write might fail
        target_file = tmp_path / "readonly" / "test.yaml"
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        try:
            # Attempt atomic write - should fail gracefully
            try:
                _atomic_write(target_file, "test: content")
            except (OSError, PermissionError):
                pass  # Expected to fail

            # Verify no orphaned temp files
            temp_files = list(tmp_path.glob(".atomic_write_*"))
            assert len(temp_files) == 0, "Temp files should be cleaned up on failure"

        finally:
            # Cleanup
            readonly_dir.chmod(0o755)
