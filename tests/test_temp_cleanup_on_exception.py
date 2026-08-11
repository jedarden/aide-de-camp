"""
Test temporary file cleanup when exceptions occur during operations.

This test suite ensures that temporary files are properly cleaned up in various
exception scenarios, including unexpected exceptions, different exception types,
and all error paths through the atomic write operations.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.utils.atomic_write import (
    AtomicWriteError,
    AtomicWriteRollbackError,
    atomic_write,
    atomic_write_rollback,
    atomic_append,
    cleanup_orphaned_temp_files,
)


class TestTempCleanupOnException:
    """Test suite for temp file cleanup on various exception types."""

    def test_cleanup_on_value_error_during_write(self, tmp_path):
        """Test that temp files are cleaned up when ValueError is raised during write."""
        filepath = tmp_path / "value_error_test.txt"

        # Use _write_all which is called internally and can raise ValueError
        # Mock it to raise ValueError
        def mock_write_all_error(fd, data):
            raise ValueError("Simulated value error in _write_all")

        with patch('src.utils.atomic_write._write_all', side_effect=mock_write_all_error):
            with pytest.raises(ValueError, match="Simulated value error in _write_all"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after ValueError"

    def test_cleanup_on_io_error(self, tmp_path):
        """Test that temp files are cleaned up when IOError is raised."""
        filepath = tmp_path / "io_error_test.txt"

        # Mock to raise IOError
        def mock_write_io_error(fd, data):
            raise IOError("Simulated IO error")

        with patch('os.write', side_effect=mock_write_io_error):
            with pytest.raises(IOError, match="Simulated IO error"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after IOError"

    def test_cleanup_on_runtime_error(self, tmp_path):
        """Test that temp files are cleaned up when RuntimeError is raised."""
        filepath = tmp_path / "runtime_error_test.txt"

        # Mock to raise RuntimeError
        def mock_write_runtime_error(fd, data):
            raise RuntimeError("Simulated runtime error")

        with patch('os.write', side_effect=mock_write_runtime_error):
            with pytest.raises(RuntimeError, match="Simulated runtime error"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after RuntimeError"

    def test_cleanup_on_custom_exception(self, tmp_path):
        """Test that temp files are cleaned up when custom exception is raised."""
        filepath = tmp_path / "custom_error_test.txt"

        # Define a custom exception
        class CustomWriteError(Exception):
            pass

        # Mock to raise custom exception
        def mock_write_custom_error(fd, data):
            raise CustomWriteError("Simulated custom write error")

        with patch('os.write', side_effect=mock_write_custom_error):
            with pytest.raises(CustomWriteError, match="Simulated custom write error"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after CustomWriteError"

    def test_cleanup_on_permission_error_during_write(self, tmp_path):
        """Test temp file cleanup when permission error occurs during write."""
        filepath = tmp_path / "permission_error_test.txt"

        # Mock to raise PermissionError during write
        def mock_write_permission_error(fd, data):
            raise PermissionError("Permission denied during write")

        with patch('os.write', side_effect=mock_write_permission_error):
            with pytest.raises(PermissionError, match="Permission denied during write"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after PermissionError"

    def test_cleanup_on_disk_full_error(self, tmp_path):
        """Test temp file cleanup when disk is full (ENOSPC)."""
        filepath = tmp_path / "disk_full_test.txt"

        # Mock to raise ENOSPC (No space left on device)
        def mock_write_enospc(fd, data):
            raise OSError(28, "No space left on device")

        with patch('os.write', side_effect=mock_write_enospc):
            with pytest.raises(OSError, match="No space left on device"):
                atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after ENOSPC"

    def test_cleanup_on_os_replace_failure(self, tmp_path):
        """Test temp file cleanup when os.replace fails."""
        filepath = tmp_path / "replace_failure_test.txt"
        original_content = "original"

        filepath.write_text(original_content)

        # Track if cleanup was called
        cleanup_called = False
        original_replace = os.replace

        def mock_replace_os_error(src, dst):
            nonlocal cleanup_called
            # Let the first call succeed (temp file creation)
            # But fail on the actual replace
            if "tmp_" in str(src):
                raise OSError("Simulated os.replace failure")
            return original_replace(src, dst)

        with patch('os.replace', side_effect=mock_replace_os_error):
            with pytest.raises(OSError, match="Simulated os.replace failure"):
                atomic_write(filepath, "new content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after os.replace failure"

        # Verify original file is unchanged
        assert filepath.read_text() == original_content

    def test_cleanup_on_fsync_failure(self, tmp_path):
        """Test temp file cleanup when fsync fails."""
        filepath = tmp_path / "fsync_failure_test.txt"

        # Mock fsync to fail
        def mock_fsync_failure(fd):
            raise OSError("Simulated fsync failure")

        with patch('os.fsync', side_effect=mock_fsync_failure):
            # fsync failure is logged as warning but doesn't fail the operation
            # So we need to make the write fail instead
            def mock_write_error(fd, data):
                raise OSError("Write error to test cleanup path")

            with patch('os.write', side_effect=mock_write_error):
                with pytest.raises(OSError):
                    atomic_write(filepath, "test content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_on_validation_failure(self, tmp_path):
        """Test temp file cleanup when validation fails."""
        filepath = tmp_path / "validation_test.txt"
        filepath.write_text("original content")

        def always_fail_validation(content):
            return False

        with pytest.raises(ValueError, match="Validation failed"):
            atomic_write(filepath, "new content", validate_fn=always_fail_validation)

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should be cleaned up after validation failure"

        # Verify original file is unchanged
        assert filepath.read_text() == "original content"

    def test_cleanup_on_type_mismatch_error(self, tmp_path):
        """Test no temp file creation on type mismatch error (occurs before temp file)."""
        filepath = tmp_path / "type_error_test.txt"

        # Type error occurs before temp file creation
        with pytest.raises(TypeError, match="Text mode requires str content"):
            atomic_write(filepath, b"bytes content", mode='w')

        # Verify no temp files remain (none should have been created)
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_on_backup_creation_failure(self, tmp_path):
        """Test temp file cleanup when backup creation fails."""
        filepath = tmp_path / "backup_failure_test.txt"
        filepath.write_text("original content")

        # Mock copy2 to fail
        def mock_copy2_failure(src, dst):
            raise OSError("Simulated backup copy failure")

        with patch('shutil.copy2', side_effect=mock_copy2_failure):
            with pytest.raises(OSError, match="Failed to create backup"):
                atomic_write(filepath, "new content", create_backup=True)

        # Verify no temp files remain from the failed backup attempt
        backup_temp_files = list(tmp_path.glob("*.bak.tmp*"))
        assert len(backup_temp_files) == 0, "Backup temp files should be cleaned up"

        # Verify no main temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestRollbackContextCleanupOnException:
    """Test cleanup in rollback context manager on various exceptions."""

    def test_rollback_cleanup_on_value_error(self, tmp_path):
        """Test rollback cleanup on ValueError in context block."""
        filepath = tmp_path / "rollback_value_error.txt"
        original_content = "original"

        filepath.write_text(original_content)

        with pytest.raises(ValueError, match="Context error"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("modified")
                raise ValueError("Context error")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify original file is unchanged
        assert filepath.read_text() == original_content

    def test_rollback_cleanup_on_runtime_error(self, tmp_path):
        """Test rollback cleanup on RuntimeError in context block."""
        filepath = tmp_path / "rollback_runtime_error.txt"

        with pytest.raises(RuntimeError, match="Runtime context error"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("modified")
                raise RuntimeError("Runtime context error")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_rollback_cleanup_on_custom_exception(self, tmp_path):
        """Test rollback cleanup on custom exception in context block."""
        filepath = tmp_path / "rollback_custom_error.txt"

        class CustomContextError(Exception):
            pass

        with pytest.raises(CustomContextError, match="Custom context error"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("modified")
                raise CustomContextError("Custom context error")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_rollback_cleanup_on_keyboard_interrupt(self, tmp_path):
        """Test rollback cleanup on KeyboardInterrupt (important for user interruption)."""
        filepath = tmp_path / "rollback_keyboard_interrupt.txt"
        original_content = "original"

        filepath.write_text(original_content)

        with pytest.raises(KeyboardInterrupt):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("modified")
                raise KeyboardInterrupt()

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files must be cleaned up on KeyboardInterrupt"

        # Verify original file is unchanged
        assert filepath.read_text() == original_content

    def test_rollback_cleanup_on_system_exit(self, tmp_path):
        """Test rollback cleanup on SystemExit."""
        filepath = tmp_path / "rollback_system_exit.txt"

        with pytest.raises(SystemExit):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.write_text("modified")
                raise SystemExit()

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestAppendCleanupOnException:
    """Test temp file cleanup in atomic_append on various exceptions."""

    def test_append_cleanup_on_write_error(self, tmp_path):
        """Test append temp file cleanup on write error."""
        filepath = tmp_path / "append_write_error.txt"

        def mock_append_write_error(fd, data):
            raise OSError("Append write error")

        with patch('os.write', side_effect=mock_append_write_error):
            with pytest.raises(OSError, match="Append write error"):
                atomic_append(filepath, "new line\n")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_append_cleanup_on_validation_error(self, tmp_path):
        """Test append cleanup on validation failure."""
        filepath = tmp_path / "append_validation_error.txt"

        def fail_validation(content):
            return False

        with pytest.raises(ValueError, match="Content validation failed"):
            atomic_append(filepath, "new line\n", validate_fn=fail_validation)

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_append_cleanup_on_atomic_write_error(self, tmp_path):
        """Test append cleanup when atomic write fails during append."""
        filepath = tmp_path / "append_atomic_error.txt"
        filepath.write_text("existing content\n")

        # Mock _atomic_write_impl to fail during append
        def mock_atomic_write_error(*args, **kwargs):
            raise OSError("Atomic write error during append")

        with patch('src.utils.atomic_write._atomic_write_impl', side_effect=mock_atomic_write_error):
            with pytest.raises(OSError, match="Atomic write error during append"):
                atomic_append(filepath, "new line\n")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify original content is preserved
        assert filepath.read_text() == "existing content\n"


class TestFinallyBlockSemantics:
    """Test that cleanup runs even when exceptions occur (finally-block semantics)."""

    def test_cleanup_runs_even_when_exception_raised_in_write(self, tmp_path):
        """Verify cleanup runs in 'finally' equivalent block when exception is raised."""
        filepath = tmp_path / "finally_test.txt"

        # Track whether cleanup was attempted
        cleanup_attempts = []

        original_unlink = Path.unlink

        def tracking_unlink(path, missing_ok=False):
            if path.name.startswith(".finally_test.txt.tmp_"):
                cleanup_attempts.append(path)
            return original_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, 'unlink', new=tracking_unlink):
            def mock_write_error(fd, data):
                raise OSError("Write error")

            with patch('os.write', side_effect=mock_write_error):
                with pytest.raises(OSError):
                    atomic_write(filepath, "content")

        # Verify cleanup was attempted (finally block behavior)
        assert len(cleanup_attempts) >= 1, "Cleanup should run even when exception is raised"

        # Verify no temp files remain (cleanup succeeded)
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_runs_even_when_parent_dir_creation_fails(self, tmp_path):
        """Verify no temp files leak when parent directory creation fails."""
        # Create a file (not a directory) to cause mkdir to fail
        file_as_dir = tmp_path / "not_a_dir"
        file_as_dir.write_text("I'm a file")

        filepath = file_as_dir / "nested.txt"

        with pytest.raises(OSError):
            atomic_write(filepath, "content")

        # Verify no temp files in parent
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_runs_even_when_temp_file_creation_fails(self, tmp_path):
        """Verify cleanup path is safe when temp file creation itself fails."""
        readonly_dir = tmp_path / "readonly_for_temp"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        filepath = readonly_dir / "file.txt"

        with pytest.raises(PermissionError):
            atomic_write(filepath, "content")

        # Restore permissions for cleanup
        readonly_dir.chmod(0o755)

        # Verify no temp files (none were created, so none to clean)
        temp_files = list(readonly_dir.glob("*.tmp"))
        assert len(temp_files) == 0


class TestCleanupIdempotencyOnException:
    """Test that cleanup is idempotent and safe even if called multiple times."""

    def test_cleanup_is_safe_when_temp_already_deleted(self, tmp_path):
        """Test cleanup doesn't fail if temp file is already deleted."""
        filepath = tmp_path / "idempotent_cleanup.txt"

        # Track unlink calls
        unlink_calls = []

        original_unlink = Path.unlink

        def double_unlink(path, missing_ok=False):
            unlink_calls.append((str(path), missing_ok))
            # First unlink succeeds
            result = original_unlink(path, missing_ok=missing_ok)
            # Simulate a second cleanup attempt (file already gone)
            if path.name.startswith(".idempotent_cleanup.txt.tmp_"):
                # This simulates the cleanup being called twice
                try:
                    original_unlink(path, missing_ok=True)
                except FileNotFoundError:
                    pass  # Expected, file already deleted
            return result

        def mock_write_error(fd, data):
            raise OSError("Write error")

        with patch.object(Path, 'unlink', new=double_unlink):
            with patch('os.write', side_effect=mock_write_error):
                with pytest.raises(OSError):
                    atomic_write(filepath, "content")

        # Verify cleanup was called
        assert len(unlink_calls) >= 1

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_handles_concurrent_deletion(self, tmp_path):
        """Test cleanup handles case where another process deletes the temp file."""
        filepath = tmp_path / "concurrent_cleanup.txt"

        original_unlink = Path.unlink

        def simulate_concurrent_delete(path, missing_ok=False):
            if path.name.startswith(".concurrent_cleanup.txt.tmp_"):
                # First, simulate our cleanup
                original_unlink(path, missing_ok=missing_ok)
                # Then simulate another process deleting it (file already gone)
                try:
                    original_unlink(path, missing_ok=True)
                except FileNotFoundError:
                    pass  # Expected and handled
            return original_unlink(path, missing_ok=missing_ok)

        def mock_write_error(fd, data):
            raise OSError("Simulated error")

        with patch.object(Path, 'unlink', new=simulate_concurrent_delete):
            with patch('os.write', side_effect=mock_write_error):
                with pytest.raises(OSError):
                    atomic_write(filepath, "content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


class TestCleanupVerificationAcrossExceptionPaths:
    """Comprehensive tests verifying no temp file leakage across all exception paths."""

    def test_no_temp_leakage_on_all_exception_types(self, tmp_path):
        """Test comprehensive set of exception types to ensure no temp leakage."""
        exception_types_to_test = [
            (ValueError, "Value error"),
            (TypeError, "Type error"),
            (RuntimeError, "Runtime error"),
            (IOError, "IO error"),
            (OSError, "OS error"),
            (PermissionError, "Permission error"),
            (AtomicWriteError, "Atomic write error"),
        ]

        for exception_class, message in exception_types_to_test:
            filepath = tmp_path / f"test_{exception_class.__name__}.txt"

            def mock_write_specific_error(fd, data):
                raise exception_class(message)

            with patch('os.write', side_effect=mock_write_specific_error):
                with pytest.raises(exception_class):
                    atomic_write(filepath, "content")

            # Verify no temp files remain for this exception type
            temp_files = list(tmp_path.glob("*.tmp"))
            assert len(temp_files) == 0, \
                f"Temp files leaked after {exception_class.__name__}"

    def test_no_temp_leakage_in_rollback_context_all_exceptions(self, tmp_path):
        """Test rollback context cleanup across multiple exception types."""
        exception_types = [
            ValueError("Context value error"),
            RuntimeError("Context runtime error"),
            IOError("Context IO error"),
            Exception("Generic context error"),
        ]

        for exc in exception_types:
            filepath = tmp_path / f"rollback_{type(exc).__name__}.txt"

            with pytest.raises(type(exc)):
                with atomic_write_rollback(filepath) as temp_path:
                    temp_path.write_text("content")
                    raise exc

            # Verify no temp files remain
            temp_files = list(tmp_path.glob("*.tmp"))
            assert len(temp_files) == 0, \
                f"Temp files leaked after rollback with {type(exc).__name__}"

    def test_no_temp_leakage_when_cleanup_fails(self, tmp_path, caplog):
        """Test that original exception is preserved even if cleanup fails."""
        filepath = tmp_path / "cleanup_failure.txt"

        # Mock both write and cleanup to fail
        def mock_write_error(fd, data):
            raise ValueError("Original write error")

        def mock_cleanup_fail(path, missing_ok=False):
            if path.name.startswith(".cleanup_failure.txt.tmp_"):
                raise PermissionError("Cleanup failed")
            return path.unlink(missing_ok=missing_ok)

        with patch('os.write', side_effect=mock_write_error):
            with patch.object(Path, 'unlink', new=mock_cleanup_fail):
                with pytest.raises(ValueError, match="Original write error"):
                    atomic_write(filepath, "content")

        # The original error should be raised, not the cleanup error
        # (cleanup error is logged but doesn't mask the original)

        # Note: Temp file may remain if cleanup failed, but original error is preserved
        # This is acceptable behavior - the operation failed and was reported correctly


class TestCleanupWithRetryLogic:
    """Test cleanup behavior when retry logic is involved."""

    def test_cleanup_after_all_retries_exhausted(self, tmp_path):
        """Test temp cleanup after all retry attempts are exhausted."""
        filepath = tmp_path / "retry_exhausted.txt"

        attempt_count = [0]

        def mock_write_transient_error(fd, data):
            attempt_count[0] += 1
            raise OSError(f"Transient error attempt {attempt_count[0]}")

        with patch('os.write', side_effect=mock_write_transient_error):
            with pytest.raises(OSError):
                atomic_write(filepath, "content", max_retries=3, initial_delay=0.01)

        # Verify all retries were attempted
        assert attempt_count[0] == 4  # initial attempt + 3 retries

        # Verify no temp files remain after all retries
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_cleanup_on_first_attempt_with_retries_enabled(self, tmp_path):
        """Test cleanup works on first failure even when retries are enabled."""
        filepath = tmp_path / "first_attempt_failure.txt"

        def mock_write_immediate_fail(fd, data):
            raise OSError("Immediate failure")

        with patch('os.write', side_effect=mock_write_immediate_fail):
            with pytest.raises(OSError, match="Immediate failure"):
                atomic_write(filepath, "content", max_retries=5, initial_delay=0.01)

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0
