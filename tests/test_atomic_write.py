"""
Unit tests for atomic_write utility.
"""

import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.utils.atomic_write import (
    atomic_write,
    atomic_write_rollback,
    cleanup_orphaned_temp_files,
    AtomicWriteRollbackError,
    AtomicWriteError
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
        from src.utils.atomic_write import logger

        filepath = tmp_path / "log_test.txt"

        with caplog.at_level(logging.INFO, logger='src.utils.atomic_write'):
            atomic_write(filepath, "content")

        # Should have INFO log entries
        assert any('Starting atomic write' in record.message for record in caplog.records)
        assert any('completed successfully' in record.message for record in caplog.records)

    def test_failed_operation_logs_errors(self, tmp_path, caplog):
        """Test that failed operations log errors."""
        import logging
        from src.utils.atomic_write import logger

        filepath = tmp_path / "error_log_test.txt"

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
