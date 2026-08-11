"""
Unit tests for atomic_write utility.
"""

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.atomic_write import (
    AtomicWriteError,
    AtomicWriteRollbackError,
    atomic_append,
    atomic_write,
    atomic_write_rollback,
    cleanup_orphaned_temp_files,
)


class TestAtomicWrite:
    """Test suite for atomic_write function."""

    def test_writes_new_file(self, tmp_path):
        """Test that atomic_write creates a new file with correct content."""
        filepath = tmp_path / "new_file.txt"
        content = "Hello, World!"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_overwrites_existing_file(self, tmp_path):
        """Test that atomic_write correctly overwrites an existing file."""
        filepath = tmp_path / "existing_file.txt"
        original_content = "Original content"
        new_content = "New content"

        # Create file with original content
        filepath.write_text(original_content)

        # Overwrite with new content
        atomic_write(filepath, new_content)

        assert filepath.read_text() == new_content

    def test_creates_parent_directories(self, tmp_path):
        """Test that atomic_write creates parent directories if needed."""
        filepath = tmp_path / "deep" / "nested" / "file.txt"
        content = "Content in nested path"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_binary_mode(self, tmp_path):
        """Test that atomic_write works in binary mode."""
        filepath = tmp_path / "binary_file.bin"
        content = b"\x00\x01\x02\x03\xff\xfe"

        atomic_write(filepath, content, mode='wb')

        assert filepath.exists()
        assert filepath.read_bytes() == content

    def test_empty_content(self, tmp_path):
        """Test that atomic_write handles empty content correctly."""
        filepath = tmp_path / "empty.txt"
        atomic_write(filepath, "")
        assert filepath.exists()
        assert filepath.read_text() == ""

    def test_unicode_content(self, tmp_path):
        """Test that atomic_write handles Unicode characters correctly."""
        filepath = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_type_error_text_mode_with_bytes(self, tmp_path):
        """Test that passing bytes to text mode raises TypeError."""
        filepath = tmp_path / "test.txt"
        content = b"bytes content"

        with pytest.raises(TypeError, match="Text mode requires str content"):
            atomic_write(filepath, content, mode='w')

    def test_type_error_binary_mode_with_str(self, tmp_path):
        """Test that passing str to binary mode raises TypeError."""
        filepath = tmp_path / "test.bin"
        content = "string content"

        with pytest.raises(TypeError, match="Binary mode requires bytes content"):
            atomic_write(filepath, content, mode='wb')

    def test_permission_error_on_readonly_directory(self, tmp_path):
        """Test that permission error is raised when directory is not writable."""
        # Create a read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        filepath = readonly_dir / "file.txt"

        with pytest.raises(PermissionError):
            atomic_write(filepath, "content")

    def test_atomicity_on_same_filesystem(self, tmp_path):
        """Test that writes appear atomic (all-or-nothing)."""
        filepath = tmp_path / "atomic_test.txt"
        original_content = "Original"
        new_content = "New" * 1000  # Larger content to test actual rename

        # Write original content
        filepath.write_text(original_content)

        # Perform atomic overwrite
        atomic_write(filepath, new_content)

        # Verify file has complete new content (not partial)
        result = filepath.read_text()
        assert result == new_content
        assert len(result) == len(new_content)

    def test_pathlib_path_support(self, tmp_path):
        """Test that atomic_write accepts pathlib.Path objects."""
        filepath = tmp_path / "pathlib_test.txt"
        content = "Pathlib support test"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_string_path_support(self, tmp_path):
        """Test that atomic_write accepts string paths."""
        filepath = str(tmp_path / "string_path.txt")
        content = "String path support test"

        atomic_write(filepath, content)

        assert Path(filepath).exists()
        assert Path(filepath).read_text() == content


class TestAtomicWriteBackup:
    """Test backup creation functionality."""

    def test_creates_backup_when_requested(self, tmp_path):
        """Test that backup is created when create_backup=True."""
        filepath = tmp_path / "original.txt"
        original_content = "Original content"

        filepath.write_text(original_content)

        backup_path = atomic_write(filepath, "New content", create_backup=True)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.read_text() == original_content
        assert filepath.read_text() == "New content"

    def test_backup_none_for_new_file(self, tmp_path):
        """Test that backup is None when creating new file."""
        filepath = tmp_path / "new_file.txt"

        backup_path = atomic_write(filepath, "New content", create_backup=True)

        assert backup_path is None
        assert filepath.exists()

    def test_backup_preserves_permissions(self, tmp_path):
        """Test that backup preserves file permissions."""
        filepath = tmp_path / "original.txt"
        original_content = "Original content"

        filepath.write_text(original_content)
        filepath.chmod(0o644)  # Set specific permissions

        atomic_write(filepath, "New content", create_backup=True)

        backup_path = tmp_path / "original.txt.bak"
        # Check backup exists and has similar permissions
        assert backup_path.exists()
        # Permissions should be preserved (rough check)
        assert backup_path.stat().st_mode & 0o777 == 0o644

    def test_backup_publication_failure_preserves_existing_backup(self, tmp_path):
        """A failed backup replace must not corrupt the previous backup."""
        filepath = tmp_path / "original.txt"
        backup_path = tmp_path / "original.txt.bak"
        filepath.write_text("Original content")
        backup_path.write_text("Previous backup")

        real_replace = os.replace

        def fail_backup_replace(source, destination):
            if Path(destination) == backup_path:
                raise OSError("simulated backup publication failure")
            return real_replace(source, destination)

        with patch("src.utils.atomic_write.os.replace", side_effect=fail_backup_replace):
            with pytest.raises(OSError, match="simulated backup publication failure"):
                atomic_write(filepath, "New content", create_backup=True)

        assert filepath.read_text() == "Original content"
        assert backup_path.read_text() == "Previous backup"
        assert not list(tmp_path.glob(".original.txt.bak.tmp_*.bak"))


class TestAtomicWriteRollbackSerialization:
    """Test rollback-context publication and ownership semantics."""

    def test_rollback_serializes_same_target_transactions(self, tmp_path):
        """A second transaction cannot enter while the first owns the target."""
        filepath = tmp_path / "serialized.txt"
        first_ready = threading.Event()
        second_attempted = threading.Event()
        second_entered = threading.Event()
        allow_first_to_commit = threading.Event()
        errors = []

        def first_writer():
            try:
                with atomic_write_rollback(filepath) as temp_path:
                    temp_path.write_text("first")
                    first_ready.set()
                    allow_first_to_commit.wait(timeout=2)
            except BaseException as error:  # pragma: no cover - assertion below reports it
                errors.append(error)

        def second_writer():
            try:
                first_ready.wait(timeout=2)
                second_attempted.set()
                with atomic_write_rollback(filepath) as temp_path:
                    second_entered.set()
                    temp_path.write_text("second")
            except BaseException as error:  # pragma: no cover - assertion below reports it
                errors.append(error)

        first_thread = threading.Thread(target=first_writer)
        second_thread = threading.Thread(target=second_writer)
        first_thread.start()
        assert first_ready.wait(timeout=2)
        second_thread.start()
        assert second_attempted.wait(timeout=2)

        # The first context still owns the per-path lock, so the second
        # transaction cannot even allocate its staging file yet.
        assert not second_entered.is_set()

        allow_first_to_commit.set()
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()
        assert errors == []
        assert filepath.read_text() == "second"


class TestAtomicWriteValidation:
    """Test validation functionality."""

    def test_validation_passes(self, tmp_path):
        """Test that valid content passes validation."""
        filepath = tmp_path / "config.json"
        content = '{"key": "value"}'

        def is_json(content_str):
            try:
                json.loads(content_str)
                return True
            except json.JSONDecodeError:
                return False

        atomic_write(filepath, content, validate_fn=is_json)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_validation_fails(self, tmp_path):
        """Test that invalid content raises ValueError."""
        filepath = tmp_path / "config.json"
        invalid_content = '{"key": invalid}'

        def is_json(content_str):
            try:
                json.loads(content_str)
                return True
            except json.JSONDecodeError:
                return False

        with pytest.raises(ValueError, match="Validation failed"):
            atomic_write(filepath, invalid_content, validate_fn=is_json)

        # Original file should be unchanged if it existed
        filepath.write_text('{"old": "data"}')
        with pytest.raises(ValueError, match="Validation failed"):
            atomic_write(filepath, invalid_content, validate_fn=is_json)
        assert filepath.read_text() == '{"old": "data"}'


class TestAtomicWriteRollback:
    """Test atomic write with rollback context manager."""

    def test_rollback_context_successful_write(self, tmp_path):
        """Test successful write using rollback context."""
        filepath = tmp_path / "context_test.txt"

        with atomic_write_rollback(filepath) as temp_path:
            temp_path.write_text("Content from context")

        assert filepath.exists()
        assert filepath.read_text() == "Content from context"

    def test_rollback_context_successful_binary_write(self, tmp_path):
        """Test successful binary write using rollback context."""
        filepath = tmp_path / "binary_context.bin"

        with atomic_write_rollback(filepath, mode='wb') as temp_path:
            temp_path.write_bytes(b"\x00\x01\x02\x03")

        assert filepath.exists()
        assert filepath.read_bytes() == b"\x00\x01\x02\x03"

    def test_rollback_context_exception_cleanup(self, tmp_path):
        """Test that exception in context rolls back changes."""
        filepath = tmp_path / "rollback_test.txt"
        original_content = "Original content"

        filepath.write_text(original_content)

        with pytest.raises(ValueError, match="Simulated error"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("Partial content")
                raise ValueError("Simulated error")

        # File should be unchanged
        assert filepath.exists()
        assert filepath.read_text() == original_content

        # No temp files should remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_rollback_context_preserves_original(self, tmp_path):
        """Test that rollback preserves original file content."""
        filepath = tmp_path / "preserve_test.txt"
        original_content = "This must be preserved"

        filepath.write_text(original_content)

        try:
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("This should not stick")
                raise RuntimeError("Intentional failure")
        except RuntimeError:
            pass

        # Original content should be intact
        assert filepath.read_text() == original_content

    def test_rollback_tolerates_temp_file_removed_by_another_cleanup(self, tmp_path):
        """A repeated/concurrent rollback is successful once the temp is absent."""
        filepath = tmp_path / "rollback_race.txt"

        with pytest.raises(ValueError, match="original failure"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("discarded")
                # Simulate another cleanup owner winning the unlink race.
                temp_path.unlink()
                raise ValueError("original failure")

        assert not filepath.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_rollback_cleanup_failure_is_logged_and_reported(self, tmp_path, caplog):
        """A locked staging file is reported as an incomplete rollback."""
        filepath = tmp_path / "rollback_locked.txt"
        real_unlink = Path.unlink

        def fail_temp_unlink(path, missing_ok=False):
            if path.name.startswith(f".{filepath.name}.tmp_"):
                raise PermissionError("resource is locked")
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", new=fail_temp_unlink):
            with caplog.at_level("ERROR", logger="src.utils.atomic_write"):
                with pytest.raises(AtomicWriteRollbackError, match="resource is locked"):
                    with atomic_write_rollback(filepath) as temp_path:
                        temp_path.write_text("discarded")
                        raise ValueError("operation failed")

        assert any(
            "Permission denied cleaning up temp file" in record.message
            and str(filepath.name) in record.message
            for record in caplog.records
        )


class TestAtomicWriteErrors:
    """Test error handling scenarios."""

    def test_disk_full_error_simulation(self, tmp_path):
        """Test handling of disk full error."""
        filepath = tmp_path / "disk_full_test.txt"

        # Mock os.write to simulate disk full error
        def mock_write_raise_enospc(fd, data):
            raise OSError(28, "No space left on device")  # ENOSPC

        with patch('os.write', side_effect=mock_write_raise_enospc):
            with pytest.raises(OSError, match="No space left on device"):
                atomic_write(filepath, "Large content")

        # No temp files should remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_invalid_mode_error(self, tmp_path):
        """Test that invalid mode raises ValueError."""
        filepath = tmp_path / "mode_test.txt"

        with pytest.raises(ValueError, match="Invalid mode"):
            atomic_write(filepath, "content", mode='invalid')

    def test_temp_file_cleanup_on_write_error(self, tmp_path):
        """Test that temp file is cleaned up on write error."""
        filepath = tmp_path / "cleanup_test.txt"

        # Mock os.write to fail
        def mock_write_raise_error(fd, data):
            raise OSError("Simulated write error")

        with patch('os.write', side_effect=mock_write_raise_error):
            with pytest.raises(OSError):
                atomic_write(filepath, "content")

        # No temp files should remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_parent_directory_creation_error(self, tmp_path):
        """Test handling of parent directory creation error."""
        # Create a file instead of directory
        file_as_dir = tmp_path / "not_a_directory"
        file_as_dir.write_text("I'm a file, not a directory")

        filepath = file_as_dir / "nested.txt"

        with pytest.raises(OSError):
            atomic_write(filepath, "content")


class TestOrphanedTempFileCleanup:
    """Test orphaned temp file cleanup functionality."""

    def test_cleanup_orphaned_temp_files(self, tmp_path):
        """Test cleanup of orphaned temp files."""
        # Create some orphaned temp files
        for i in range(3):
            temp_file = tmp_path / f"orphaned_{i}.tmp"
            temp_file.write_text(f"orphaned content {i}")

        # Create a non-temp file
        regular_file = tmp_path / "regular.txt"
        regular_file.write_text("regular content")

        # Clean up temp files
        count = cleanup_orphaned_temp_files(tmp_path, "*.tmp")

        assert count == 3
        assert regular_file.exists()

    def test_cleanup_specific_pattern(self, tmp_path):
        """Test cleanup with specific pattern."""
        # Create files with different patterns
        for i in range(2):
            (tmp_path / f"temp_{i}.tmp").write_text(f"temp {i}")
        for i in range(2):
            (tmp_path / f"backup_{i}.bak").write_text(f"backup {i}")

        # Clean up only .tmp files
        count = cleanup_orphaned_temp_files(tmp_path, "*.tmp")

        assert count == 2
        # Backup files should remain
        assert len(list(tmp_path.glob("*.bak"))) == 2

    def test_cleanup_nonexistent_directory(self):
        """Test cleanup on non-existent directory."""
        # Should not raise error, just return 0
        count = cleanup_orphaned_temp_files("/nonexistent/path", "*.tmp")
        assert count == 0

    def test_cleanup_is_idempotent(self, tmp_path):
        """Calling orphan cleanup repeatedly is safe and has no residual state."""
        for index in range(2):
            (tmp_path / f"repeat_{index}.tmp").write_text("orphan")

        assert cleanup_orphaned_temp_files(tmp_path, "*.tmp") == 2
        assert cleanup_orphaned_temp_files(tmp_path, "*.tmp") == 0
        assert list(tmp_path.glob("*.tmp")) == []

    def test_cleanup_treats_concurrent_missing_file_as_success(self, tmp_path):
        """A file removed between discovery and unlink is not a failure."""
        temp_file = tmp_path / "raced.tmp"
        temp_file.write_text("orphan")
        real_unlink = Path.unlink

        def report_missing(path, missing_ok=False):
            if path == temp_file:
                raise FileNotFoundError(path)
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", new=report_missing):
            result = cleanup_orphaned_temp_files(tmp_path, "*.tmp", return_details=True)

        assert result["cleaned"] == 0
        assert result["failed"] == 0
        assert result["errors"] == []
        temp_file.unlink()


class TestAtomicAppendCleanup:
    """The append commit must not be retried because staging cleanup failed."""

    def test_successful_append_survives_locked_staging_cleanup(self, tmp_path, caplog):
        filepath = tmp_path / "append.log"
        real_unlink = Path.unlink

        def fail_temp_unlink(path, missing_ok=False):
            if path.name.startswith(".tmp_append_"):
                raise PermissionError("staging resource is locked")
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", new=fail_temp_unlink):
            with caplog.at_level("ERROR", logger="src.utils.atomic_write"):
                atomic_append(filepath, "one\n")

        # The replace is the append commit point.  A cleanup failure must not
        # cause a caller retry that duplicates this record.
        assert filepath.read_text() == "one\n"
        assert any(
            "successful atomic append" in record.message
            and "staging resource is locked" in record.message
            for record in caplog.records
        )


class TestAtomicWriteErrorTypes:
    """Test custom error types."""

    def test_atomic_write_error_base_class(self):
        """Test that AtomicWriteError is a proper exception base."""
        error = AtomicWriteError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_atomic_write_rollback_error(self):
        """Test AtomicWriteRollbackError specific behavior."""
        error = AtomicWriteRollbackError("Rollback failed")
        assert isinstance(error, AtomicWriteError)
        assert isinstance(error, Exception)
        assert str(error) == "Rollback failed"


class TestAtomicWriteLogging:
    """Test logging behavior."""

    def test_successful_operation_logs(self, tmp_path, caplog):
        """Test that successful operations are logged."""
        import logging

        filepath = tmp_path / "log_test.txt"

        with caplog.at_level(logging.INFO, logger='src.utils.atomic_write'):
            atomic_write(filepath, "content")

        # Should have INFO log entries
        assert any('Starting atomic write' in record.message for record in caplog.records)
        assert any('completed successfully' in record.message for record in caplog.records)

    def test_failed_operation_logs_errors(self, tmp_path, caplog):
        """Test that failed operations log errors."""
        import logging

        # Force a permission error
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        with caplog.at_level(logging.ERROR, logger='src.utils.atomic_write'):
            try:
                atomic_write(readonly_dir / "file.txt", "content")
            except PermissionError:
                pass

        # Should have ERROR log entries
        assert any('Permission denied' in record.message or
                   'readonly' in record.message or
                   'error' in record.message.lower()
                   for record in caplog.records)


class TestConcurrentAtomicWrite:
    """Test concurrent access to atomic_write function."""

    def test_concurrent_writes_do_not_corrupt_data(self, tmp_path):
        """Test that concurrent writes do not corrupt data."""
        filepath = tmp_path / "concurrent_test.txt"
        num_writers = 10
        errors = []
        successful_writes = []

        def writer(writer_id: int):
            try:
                content = f"Writer {writer_id} content " * 100  # Substantial content
                atomic_write(filepath, content)
                successful_writes.append(writer_id)
            except Exception as e:
                errors.append((writer_id, e))

        # Launch all writers concurrently
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=5)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify file exists and has content from exactly one writer
        assert filepath.exists(), "File should exist after concurrent writes"
        final_content = filepath.read_text()

        # Content should be complete and from exactly one writer
        assert len(final_content) > 0, "File should have content"

        # Verify content matches one of the writers' expected patterns
        valid_content = False
        for writer_id in range(num_writers):
            expected_pattern = f"Writer {writer_id} content " * 100
            if final_content == expected_pattern:
                valid_content = True
                break

        assert valid_content, f"Final content does not match any writer's expected pattern. Length: {len(final_content)}"

        # Verify exactly one writer won (all completed, but file has only one content)
        # This is validated by the content check above - atomicity ensures one complete write

    def test_one_writer_wins_under_contention(self, tmp_path):
        """Test that one writer wins cleanly under contention."""
        filepath = tmp_path / "contention_test.txt"
        num_writers = 20
        write_barrier = threading.Barrier(num_writers)
        errors = []
        completion_order = []

        def writer(writer_id: int):
            try:
                # Synchronize all writers to start simultaneously
                write_barrier.wait(timeout=5)

                content = f"Winner-{writer_id}:" + "x" * 1000
                atomic_write(filepath, content)
                completion_order.append(writer_id)
            except Exception as e:
                errors.append((writer_id, e))

        # Launch all writers simultaneously
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=10)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify file has exactly one writer's content
        assert filepath.exists(), "File should exist"
        final_content = filepath.read_text()

        # Extract which writer won from content pattern
        winner_match = None
        for writer_id in range(num_writers):
            expected_prefix = f"Winner-{writer_id}:"
            if final_content.startswith(expected_prefix):
                winner_match = writer_id
                break

        assert winner_match is not None, f"Could not identify winner from content: {final_content[:100]}"

        # Verify content is complete
        expected_content = f"Winner-{winner_match}:" + "x" * 1000
        assert final_content == expected_content, "Content should be complete from winning writer"

        # Verify exactly one winner (content integrity check above ensures this)
        # The atomic replace guarantees one complete content wins

    def test_locking_serializes_writes(self, tmp_path):
        """Test that locking mechanism properly serializes write operations."""
        filepath = tmp_path / "serialized_test.txt"
        num_writers = 5
        write_count = [0]  # Use list to share across threads
        lock = threading.Lock()
        in_write_zone = threading.Event()
        ready_to_exit = threading.Event()
        errors = []

        def tracked_writer(writer_id: int):
            try:
                # First writer enters zone and signals
                with lock:
                    my_turn = write_count[0]
                    write_count[0] += 1

                # Only the first writer waits in the critical zone
                if my_turn == 0:
                    in_write_zone.set()
                    # Hold while others try to acquire
                    ready_to_exit.wait(timeout=5)
                else:
                    # Others wait for first to signal it's in zone
                    in_write_zone.wait(timeout=2)

                # Now perform the actual write
                atomic_write(filepath, f"Write {writer_id}")

            except Exception as e:
                errors.append((writer_id, e))

        # Start first writer
        t1 = threading.Thread(target=tracked_writer, args=(0,))
        t1.start()

        # Wait for first writer to enter zone
        assert in_write_zone.wait(timeout=2), "First writer should signal it's in write zone"

        # Start remaining writers while first is holding
        threads = [t1]
        for i in range(1, num_writers):
            t = threading.Thread(target=tracked_writer, args=(i,))
            threads.append(t)
            t.start()

        # Give other writers time to queue up on the lock
        import time
        time.sleep(0.2)

        # Release first writer
        ready_to_exit.set()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=5)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify final state is consistent (one writer won)
        assert filepath.exists()
        final_content = filepath.read_text()
        assert final_content.startswith("Write ")  # Valid content pattern

    def test_high_contention_stress_test(self, tmp_path):
        """Test atomic write under high contention with many concurrent writers."""
        filepath = tmp_path / "stress_test.txt"
        num_writers = 50
        errors = []
        success_count = [0]

        def stress_writer(writer_id: int):
            try:
                # Each writer attempts multiple times
                for attempt in range(3):
                    content = f"S{writer_id}-A{attempt}:" + "y" * 500
                    atomic_write(filepath, content)
                    success_count[0] += 1
                    import time
                    time.sleep(0.001)  # Small delay to increase contention
            except Exception as e:
                errors.append((writer_id, attempt, e))

        # Launch all writers
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=stress_writer, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=15)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred during stress test: {errors}"

        # Verify all writes succeeded
        assert success_count[0] == num_writers * 3, f"Expected {num_writers * 3} writes, got {success_count[0]}"

        # Verify final file is valid
        assert filepath.exists()
        final_content = filepath.read_text()

        # Verify content is complete (not truncated or corrupted)
        assert len(final_content) > 500, "Content should be substantial"
        assert final_content.endswith("y" * 500), "Content should end with expected pattern"

    def test_concurrent_writes_with_backup(self, tmp_path):
        """Test concurrent writes with backup creation."""
        filepath = tmp_path / "backup_concurrent.txt"
        num_writers = 8
        errors = []

        def backup_writer(writer_id: int):
            try:
                content = f"Backup-{writer_id}:" + "z" * 200
                atomic_write(filepath, content, create_backup=True)
            except Exception as e:
                errors.append((writer_id, e))

        # Create initial file
        filepath.write_text("Initial content")

        # Launch concurrent writers with backup
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=backup_writer, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify final state
        assert filepath.exists()
        final_content = filepath.read_text()

        # Should have content from one writer
        valid_content = False
        for writer_id in range(num_writers):
            expected = f"Backup-{writer_id}:" + "z" * 200
            if final_content == expected:
                valid_content = True
                break

        assert valid_content, "Final content should match one writer's pattern"


class TestConcurrentAtomicAppend:
    """Test concurrent access to atomic_append function."""

    def test_concurrent_appends_record_all_data(self, tmp_path):
        """Test that concurrent appends record all data without loss."""
        filepath = tmp_path / "concurrent_append.log"
        num_appenders = 10
        records_per_appender = 5
        errors = []

        def appender(appender_id: int):
            try:
                for i in range(records_per_appender):
                    record = f"appender-{appender_id}-record-{i}\n"
                    atomic_append(filepath, record)
            except Exception as e:
                errors.append((appender_id, e))

        # Launch all appenders concurrently
        threads = []
        for i in range(num_appenders):
            t = threading.Thread(target=appender, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all records were written
        assert filepath.exists()
        lines = filepath.read_text().splitlines()

        # Should have all records (order may vary due to locking)
        expected_count = num_appenders * records_per_appender
        assert len(lines) == expected_count, f"Expected {expected_count} lines, got {len(lines)}"

        # Verify all records are present and complete
        for appender_id in range(num_appenders):
            for record_id in range(records_per_appender):
                expected_line = f"appender-{appender_id}-record-{record_id}"
                assert expected_line in lines, f"Missing record: {expected_line}"

    def test_concurrent_append_with_existing_content(self, tmp_path):
        """Test concurrent appends preserve existing content."""
        filepath = tmp_path / "append_existing.txt"
        initial_lines = ["initial-1", "initial-2", "initial-3"]
        filepath.write_text("\n".join(initial_lines) + "\n")

        num_appenders = 5
        errors = []

        def appender(appender_id: int):
            try:
                record = f"appended-{appender_id}\n"
                atomic_append(filepath, record)
            except Exception as e:
                errors.append((appender_id, e))

        # Launch concurrent appenders
        threads = []
        for i in range(num_appenders):
            t = threading.Thread(target=appender, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify initial content is preserved
        lines = filepath.read_text().splitlines()
        for initial_line in initial_lines:
            assert initial_line in lines, f"Initial line lost: {initial_line}"

        # Verify all appended records are present
        assert len(lines) == len(initial_lines) + num_appenders

    def test_high_contention_append_stress(self, tmp_path):
        """Test atomic_append under high contention."""
        filepath = tmp_path / "append_stress.log"
        num_appenders = 20
        records_per_appender = 10
        errors = []
        barrier = threading.Barrier(num_appenders)

        def stress_appender(appender_id: int):
            try:
                # Synchronize start
                barrier.wait(timeout=5)

                for i in range(records_per_appender):
                    record = f"S{appender_id}-R{i}\n"
                    atomic_append(filepath, record)
            except Exception as e:
                errors.append((appender_id, e))

        # Launch all appenders
        threads = []
        for i in range(num_appenders):
            t = threading.Thread(target=stress_appender, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=15)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all records present
        lines = filepath.read_text().splitlines()
        expected_count = num_appenders * records_per_appender
        assert len(lines) == expected_count, f"Expected {expected_count} records, got {len(lines)}"


class TestMixedConcurrentOperations:
    """Test mixed concurrent atomic_write and atomic_append operations."""

    def test_concurrent_write_and_append_do_not_corrupt(self, tmp_path):
        """Test that concurrent writes and appends maintain data integrity."""
        filepath = tmp_path / "mixed_operations.txt"
        num_writers = 5
        num_appenders = 5
        errors = []

        # Initialize with content
        filepath.write_text("initial\n")

        def writer(writer_id: int):
            try:
                content = f"writer-{writer_id}\n"
                atomic_write(filepath, content)
            except Exception as e:
                errors.append(("writer", writer_id, e))

        def appender(appender_id: int):
            try:
                content = f"appender-{appender_id}\n"
                atomic_append(filepath, content)
            except Exception as e:
                errors.append(("appender", appender_id, e))

        # Launch mixed operations
        threads = []
        for i in range(num_writers):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
            t.start()

        for i in range(num_appenders):
            t = threading.Thread(target=appender, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=10)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify file is valid and not corrupted
        assert filepath.exists()
        content = filepath.read_text()
        lines = content.splitlines()

        # Should have at least one line
        assert len(lines) > 0, "File should have content"

        # All lines should be valid (no partial or corrupted records)
        for line in lines:
            assert line.startswith(("writer-", "appender-", "initial")), f"Invalid line: {line}"
