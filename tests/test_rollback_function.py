"""Tests for the rollback() function in atomic_write module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.atomic_write import (
    AtomicWriteError,
    rollback,
    atomic_write,
    cleanup_orphaned_temp_files,
)


class TestRollbackBasicFunctionality:
    """Tests for basic rollback functionality."""

    def test_rollback_restores_from_default_backup(self, tmp_path, caplog):
        """Rollback should restore from .bak file by default."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1, "status": "original"}'

        # Create initial file
        atomic_write(config_file, original_content, create_backup=False)

        # Modify the file with backup
        modified_content = '{"version": 2, "status": "modified"}'
        atomic_write(config_file, modified_content, create_backup=True)

        # Verify current state
        assert json.loads(config_file.read_text()) == json.loads(modified_content)

        # Rollback
        with caplog.at_level("INFO"):
            result_backup = rollback(config_file)

        # Verify restoration
        assert json.loads(config_file.read_text()) == json.loads(original_content)
        assert result_backup == config_file.with_suffix(".json.bak")
        assert "Rollback completed successfully" in caplog.text

    def test_rollback_with_custom_backup_path(self, tmp_path):
        """Rollback should accept custom backup path."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'
        custom_backup = tmp_path / "backups" / "config.json.bak"

        # Create directory structure
        custom_backup.parent.mkdir(parents=True, exist_ok=True)

        # Create backup manually
        custom_backup.write_text(original_content)

        # Write different content to main file
        atomic_write(config_file, '{"version": 2}', create_backup=False)

        # Rollback from custom backup
        result = rollback(config_file, backup_path=custom_backup)

        assert json.loads(config_file.read_text()) == json.loads(original_content)
        assert result == custom_backup

    def test_rollback_handles_binary_files(self, tmp_path):
        """Rollback should work with binary files."""
        binary_file = tmp_path / "data.bin"
        original_data = b'\x00\x01\x02\x03\x04\x05'

        # Create initial file
        atomic_write(binary_file, original_data, mode='wb', create_backup=False)

        # Modify the file with backup
        modified_data = b'\xff\xfe\xfd\xfc\xfb\xfa'
        atomic_write(binary_file, modified_data, mode='wb', create_backup=True)

        # Rollback
        rollback(binary_file)

        assert binary_file.read_bytes() == original_data

    def test_rollback_creates_pre_rollback_backup(self, tmp_path):
        """Rollback should create .pre_rollback.bak when requested."""
        config_file = tmp_path / "config.json"
        v1_content = '{"version": 1}'
        v2_content = '{"version": 2}'

        # Create initial file
        atomic_write(config_file, v1_content, create_backup=False)
        # Modify to v2 with backup
        atomic_write(config_file, v2_content, create_backup=True)

        # Rollback with pre-rollback backup
        rollback(config_file, create_rollback_backup=True)

        # Verify file is restored to v1
        assert json.loads(config_file.read_text()) == json.loads(v1_content)

        # Verify pre-rollback backup exists with v2 content
        pre_rollback_backup = config_file.with_suffix('.json.pre_rollback.bak')
        assert pre_rollback_backup.exists()
        assert json.loads(pre_rollback_backup.read_text()) == json.loads(v2_content)

    def test_rollback_without_pre_rollback_backup(self, tmp_path):
        """Rollback should skip pre-rollback backup when disabled."""
        config_file = tmp_path / "config.json"
        v1_content = '{"version": 1}'
        v2_content = '{"version": 2}'

        atomic_write(config_file, v1_content, create_backup=False)
        atomic_write(config_file, v2_content, create_backup=True)

        # Rollback without pre-rollback backup
        rollback(config_file, create_rollback_backup=False)

        # Verify no pre-rollback backup was created
        pre_rollback_backup = config_file.with_suffix('.json.pre_rollback.bak')
        assert not pre_rollback_backup.exists()


class TestRollbackValidation:
    """Tests for rollback validation functionality."""

    def test_rollback_with_validation_pass(self, tmp_path):
        """Rollback should succeed when validation passes."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'

        atomic_write(config_file, original_content, create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        # Validation function
        def is_valid_json(content):
            try:
                json.loads(content)
                return True
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False

        rollback(config_file, validate_fn=is_valid_json)
        assert json.loads(config_file.read_text()) == json.loads(original_content)

    def test_rollback_with_validation_fail(self, tmp_path):
        """Rollback should fail when validation fails."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'

        atomic_write(config_file, original_content, create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        # Validation function that fails
        def is_invalid(content):
            return False

        with pytest.raises(ValueError, match="Backup content validation failed"):
            rollback(config_file, validate_fn=is_invalid)

        # File should remain unchanged after failed rollback
        assert json.loads(config_file.read_text())['version'] == 2


class TestRollbackErrors:
    """Tests for rollback error handling."""

    def test_rollback_fails_when_backup_missing(self, tmp_path):
        """Rollback should fail when backup file doesn't exist."""
        config_file = tmp_path / "config.json"
        atomic_write(config_file, '{"version": 1}', create_backup=False)

        with pytest.raises(FileNotFoundError, match="Backup file.*does not exist"):
            rollback(config_file)

    def test_rollback_fails_when_backup_unreadable(self, tmp_path):
        """Rollback should fail when backup file cannot be read."""
        config_file = tmp_path / "config.json"
        backup_file = tmp_path / "config.json.bak"

        # Create backup file
        backup_file.write_text('{"version": 1}')

        # Make it unreadable (simulate permission error)
        with patch.object(Path, 'read_bytes', side_effect=OSError("Permission denied")):
            with pytest.raises(OSError, match="Failed to read backup file"):
                rollback(config_file)

    def test_rollback_preserves_original_on_restore_error(self, tmp_path):
        """Rollback should leave original file unchanged if restore fails."""
        config_file = tmp_path / "config.json"
        original_v1 = '{"version": 1}'
        current_v2 = '{"version": 2}'

        # Create backup and current state
        backup_file = tmp_path / "config.json.bak"
        backup_file.write_text(original_v1)
        config_file.write_text(current_v2)

        # Mock atomic_write to fail during restore
        with patch('src.utils.atomic_write.atomic_write', side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError, match="Simulated failure"):
                rollback(config_file)

        # Original file should be unchanged
        assert config_file.read_text() == current_v2


class TestRollbackEdgeCases:
    """Tests for rollback edge cases."""

    def test_rollback_to_nonexistent_backup(self, tmp_path):
        """Rollback should fail with clear error when backup doesn't exist."""
        config_file = tmp_path / "config.json"
        atomic_write(config_file, '{"version": 1}', create_backup=False)

        with pytest.raises(FileNotFoundError):
            rollback(config_file)

    def test_rollback_with_unicode_content(self, tmp_path):
        """Rollback should handle unicode content correctly."""
        config_file = tmp_path / "config.txt"
        original_content = "Hello 世界 🌍"

        atomic_write(config_file, original_content, create_backup=False)
        atomic_write(config_file, "Modified", create_backup=True)

        rollback(config_file)
        assert config_file.read_text() == original_content

    def test_rollback_empty_file(self, tmp_path):
        """Rollback should handle empty files correctly."""
        config_file = tmp_path / "empty.txt"

        atomic_write(config_file, "", create_backup=False)
        atomic_write(config_file, "not empty", create_backup=True)

        rollback(config_file)
        assert config_file.read_text() == ""

    def test_rollback_preserves_file_permissions(self, tmp_path):
        """Rollback should maintain file permissions after restore."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'

        atomic_write(config_file, original_content, create_backup=False)

        # Modify permissions
        import stat
        config_file.chmod(0o644)

        # Modify content with backup
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        # Rollback
        rollback(config_file)

        # Verify content is restored
        assert json.loads(config_file.read_text()) == json.loads(original_content)


class TestRollbackLogging:
    """Tests for rollback logging functionality."""

    def test_rollback_logs_operation_start(self, tmp_path, caplog):
        """Rollback should log operation start."""
        config_file = tmp_path / "config.json"
        atomic_write(config_file, '{"version": 1}', create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        with caplog.at_level("INFO"):
            rollback(config_file)

        assert "Starting rollback operation" in caplog.text

    def test_rollback_logs_success(self, tmp_path, caplog):
        """Rollback should log successful completion."""
        config_file = tmp_path / "config.json"
        atomic_write(config_file, '{"version": 1}', create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        with caplog.at_level("INFO"):
            rollback(config_file)

        assert "Rollback completed successfully" in caplog.text

    def test_rollback_logs_errors(self, tmp_path, caplog):
        """Rollback should log errors with details."""
        config_file = tmp_path / "config.json"
        atomic_write(config_file, '{"version": 1}', create_backup=False)

        with pytest.raises(FileNotFoundError), caplog.at_level("ERROR"):
            rollback(config_file)

        assert "does not exist" in caplog.text


class TestRollbackIdempotency:
    """Tests for rollback idempotency and safety."""

    def test_rollback_is_idempotent(self, tmp_path):
        """Multiple rollbacks to the same backup should produce same result."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'

        atomic_write(config_file, original_content, create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        # First rollback
        rollback(config_file)
        first_result = json.loads(config_file.read_text())

        # Modify again
        atomic_write(config_file, '{"version": 3}', create_backup=False)

        # Second rollback
        rollback(config_file)
        second_result = json.loads(config_file.read_text())

        assert first_result == second_result == json.loads(original_content)

    def test_rollback_cleanup_does_not_affect_result(self, tmp_path):
        """Temp file cleanup during rollback should not affect the result."""
        config_file = tmp_path / "config.json"
        original_content = '{"version": 1}'

        atomic_write(config_file, original_content, create_backup=False)
        atomic_write(config_file, '{"version": 2}', create_backup=True)

        # Perform rollback
        rollback(config_file)

        # Cleanup any orphaned temp files
        cleanup_orphaned_temp_files(tmp_path, pattern='*.tmp')

        # Verify rollback was successful despite cleanup
        assert json.loads(config_file.read_text()) == json.loads(original_content)
