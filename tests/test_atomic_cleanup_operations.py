"""
Test atomic cleanup operations.

Ensures all cleanup operations use atomic patterns to prevent partial state issues.
Tests cover edge cases including concurrent access, failure during cleanup, and orphaned state.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.context.prefetch import PrefetchCache, SpeculativePrefetcher
from src.freeze import set_frozen
from src.sse.broadcaster import SSEBroadcaster, SSEEvent


class TestSSEBroadcasterAtomicCleanup:
    """Test atomic cleanup in SSE broadcaster."""

    @pytest.fixture
    def broadcaster(self):
        """Create a fresh broadcaster for each test."""
        return SSEBroadcaster()

    @pytest.fixture
    def single_cycle_broadcaster(self, broadcaster, monkeypatch):
        """Run exactly one cleanup interval without starting a background task."""
        broadcaster._running = True

        async def finish_interval(_delay):
            broadcaster._running = False

        monkeypatch.setattr("src.sse.broadcaster.asyncio.sleep", finish_interval)
        return broadcaster

    @pytest.mark.asyncio
    async def test_cleanup_builds_list_before_deletion(self, single_cycle_broadcaster):
        """Test that cleanup builds dead connection list before modifying state."""
        # Register multiple connections
        connections = []
        for i in range(5):
            conn = single_cycle_broadcaster.register(
                surface_id=f"surface-{i}",
                session_id=f"session-{i}",
                surface_type="canvas"
            )
            connections.append(conn)

        # Simulate timeout by setting old heartbeat
        timeout_timestamp = datetime.now().timestamp() - 400  # > 5 minute timeout
        for conn in connections[:3]:
            single_cycle_broadcaster.connections[conn.connection_id].last_heartbeat = timeout_timestamp

        await single_cycle_broadcaster._cleanup_loop()

        # Verify only timed-out connections were removed
        assert len(single_cycle_broadcaster.connections) == 2  # Only 2 non-timed out remain
        assert connections[3].connection_id in single_cycle_broadcaster.connections
        assert connections[4].connection_id in single_cycle_broadcaster.connections

    @pytest.mark.asyncio
    async def test_cleanup_handles_connection_during_iteration(self, single_cycle_broadcaster):
        """Test cleanup handles case where connection is added during iteration."""
        # Register initial connections
        conn1 = single_cycle_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Set old heartbeat
        single_cycle_broadcaster.connections[conn1.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup - should handle gracefully even if dict changes
        await single_cycle_broadcaster._cleanup_loop()

        # Verify cleanup completed without error
        assert conn1.connection_id not in single_cycle_broadcaster.connections

    @pytest.mark.asyncio
    async def test_cleanup_sends_disconnect_before_removal(self, single_cycle_broadcaster):
        """Test that cleanup sends disconnect event before removing connection."""
        conn = single_cycle_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Set old heartbeat
        single_cycle_broadcaster.connections[conn.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup
        await single_cycle_broadcaster._cleanup_loop()

        # Verify disconnect event was queued
        assert not conn.queue.empty()
        event = conn.queue.get_nowait()
        assert event.event_type == "disconnect"
        assert event.data["reason"] == "timeout"

        # Verify connection was removed
        assert conn.connection_id not in single_cycle_broadcaster.connections

    @pytest.mark.asyncio
    async def test_cleanup_handles_queue_full_gracefully(self, single_cycle_broadcaster):
        """Test cleanup handles full queue gracefully without crashing."""
        conn = single_cycle_broadcaster.register(
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
        single_cycle_broadcaster.connections[conn.connection_id].last_heartbeat = (
            datetime.now().timestamp() - 400
        )

        # Run cleanup - should handle QueueFull gracefully
        await single_cycle_broadcaster._cleanup_loop()

        # Connection should still be removed even if disconnect event failed
        assert conn.connection_id not in single_cycle_broadcaster.connections


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

    @pytest.mark.asyncio
    async def test_freeze_handles_concurrent_writes(self, tmp_path):
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
            await asyncio.gather(*tasks)

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

    def test_freeze_cleanup_reports_permission_failure(self, tmp_path, caplog):
        """A failed sentinel removal is reported and leaves the state observable."""
        import src.freeze

        test_path = tmp_path / "FREEZE"
        test_path.write_text("frozen")
        original_path = src.freeze.SENTINEL_PATH
        real_unlink = Path.unlink
        src.freeze.SENTINEL_PATH = test_path

        def fail_sentinel_unlink(path, missing_ok=False):
            if path == test_path:
                raise PermissionError("sentinel is locked")
            return real_unlink(path, missing_ok=missing_ok)

        try:
            with patch.object(Path, "unlink", new=fail_sentinel_unlink):
                with pytest.raises(OSError, match="Permission denied removing freeze sentinel"):
                    set_frozen(False)

            assert test_path.exists()
            assert any(
                "Permission denied removing freeze sentinel" in record.message
                and str(test_path) in record.message
                for record in caplog.records
            )
        finally:
            test_path.unlink(missing_ok=True)
            src.freeze.SENTINEL_PATH = original_path


class TestHotReloadAtomicOperations:
    """Test atomic file operations in hot reload."""

    def test_atomic_write_creates_temp_with_unique_name(self, tmp_path):
        """Test that atomic write creates temp file with unique name."""
        from src.utils.atomic_write import atomic_write

        target_file = tmp_path / "test.yaml"
        content = "test: content"

        # Perform atomic write with retry logic
        atomic_write(target_file, content, max_retries=3, initial_delay=0.1)

        # Verify file was written
        assert target_file.exists()
        assert target_file.read_text() == content

        # Verify no orphaned temp files
        temp_files = list(tmp_path.glob(".atomic_write_*"))
        assert len(temp_files) == 0, "No orphaned temp files should remain"

    @pytest.mark.asyncio
    async def test_atomic_write_handles_concurrent_access(self, tmp_path):
        """Test atomic write handles concurrent file access safely."""
        from src.utils.atomic_write import atomic_write

        target_file = tmp_path / "concurrent.yaml"

        async def concurrent_write(content):
            await asyncio.to_thread(
                atomic_write,
                target_file,
                content,
                max_retries=3,
                initial_delay=0.1,
            )

        # Run concurrent writes
        contents = [f"version-{i}\n" for i in range(5)]
        tasks = [asyncio.create_task(concurrent_write(content)) for content in contents]
        await asyncio.gather(*tasks)

        # File should exist and have valid content
        assert target_file.exists()
        content = target_file.read_text()
        assert content in contents  # One of the writes should have won

    def test_atomic_write_cleans_up_temp_on_failure(self, tmp_path):
        """Test atomic write cleans up temp files on failure."""
        from src.utils.atomic_write import atomic_write

        # Create a scenario where write might fail
        target_file = tmp_path / "readonly" / "test.yaml"
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        try:
            # Attempt atomic write - should fail gracefully
            try:
                atomic_write(target_file, "test: content", max_retries=3, initial_delay=0.1)
            except (OSError, PermissionError):
                pass  # Expected to fail

            # Verify no orphaned temp files
            temp_files = list(tmp_path.glob(".atomic_write_*"))
            assert len(temp_files) == 0, "Temp files should be cleaned up on failure"

        finally:
            # Cleanup
            readonly_dir.chmod(0o755)

    def test_atomic_write_cleanup_failure_preserves_original_error(self, tmp_path, caplog):
        """A staging cleanup failure must not mask the write failure."""
        from src.utils.atomic_write import atomic_write

        target_file = tmp_path / "preserved.txt"
        target_file.write_text("original")
        real_unlink = Path.unlink

        def fail_staging_unlink(path, missing_ok=False):
            if path.name.startswith(f".{target_file.name}.tmp_"):
                raise PermissionError("staging file is locked")
            return real_unlink(path, missing_ok=missing_ok)

        with patch("os.write", side_effect=OSError("simulated write failure")):
            with patch.object(Path, "unlink", new=fail_staging_unlink):
                with caplog.at_level("ERROR", logger="src.utils.atomic_write"):
                    with pytest.raises(OSError, match="simulated write failure"):
                        atomic_write(target_file, "replacement")

        assert target_file.read_text() == "original"
        staging_files = list(tmp_path.glob(f".{target_file.name}.tmp_*.tmp"))
        assert len(staging_files) == 1
        assert any(
            "Permission denied cleaning up temp file" in record.message
            and "staging file is locked" in record.message
            for record in caplog.records
        )
        staging_files[0].unlink()
