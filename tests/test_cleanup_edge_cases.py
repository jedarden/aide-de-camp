"""Deterministic edge-case and integration tests for atomic cleanup.

These tests exercise failure paths that are difficult to reproduce reliably
with real disk or permission state. Filesystem calls are patched at the
decision point, while every test still asserts the observable post-condition:
the old file is preserved, the new file is complete, or staging files are
removed (as appropriate).
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest

import src.utils.atomic_write as atomic_write_module
from src.utils.atomic_write import (
    atomic_append,
    atomic_write,
    atomic_write_rollback,
    cleanup_orphaned_temp_files,
)


def _staging_pattern(filepath: Path) -> str:
    """Return the staging-file glob used by atomic_write."""
    return f".{filepath.name}.tmp_*.tmp"


class TestAtomicWriteFailureModes:
    """Validate atomic-write behavior when publication or staging fails."""

    def test_disk_full_while_creating_backup_preserves_previous_backup(self, tmp_path):
        """A failed backup copy leaves both the source and prior backup intact."""
        filepath = tmp_path / "config.yaml"
        backup_path = tmp_path / "config.yaml.bak"
        filepath.write_text("current")
        backup_path.write_text("previous backup")

        with patch.object(
            atomic_write_module.shutil,
            "copy2",
            side_effect=OSError(28, "No space left on device"),
        ):
            with pytest.raises(OSError, match="Failed to create backup"):
                atomic_write(filepath, "replacement", create_backup=True)

        assert filepath.read_text() == "current"
        assert backup_path.read_text() == "previous backup"
        assert not list(tmp_path.glob(".config.yaml.bak.tmp_*.bak"))

    def test_retry_after_transient_publish_failure_cleans_each_staging_file(self, tmp_path):
        """A retry publishes once and removes the failed attempt's staging file."""
        filepath = tmp_path / "retry.txt"
        real_replace = atomic_write_module.os.replace
        attempts = 0

        def fail_once(source, destination):
            nonlocal attempts
            if Path(destination) == filepath and attempts == 0:
                attempts += 1
                raise OSError(28, "No space left on device")
            return real_replace(source, destination)

        with patch.object(atomic_write_module.os, "replace", side_effect=fail_once):
            with patch.object(atomic_write_module.time, "sleep") as sleep:
                atomic_write(filepath, "published", max_retries=1, initial_delay=0)

        assert attempts == 1
        assert sleep.call_count == 1
        assert filepath.read_text() == "published"
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_fsync_failure_is_nonfatal_after_complete_write(self, tmp_path, caplog):
        """An unavailable fsync does not turn a complete atomic replace into failure."""
        filepath = tmp_path / "fsync.txt"

        with patch.object(
            atomic_write_module.os,
            "fsync",
            side_effect=OSError("fsync unavailable"),
        ):
            atomic_write(filepath, "complete")

        assert filepath.read_text() == "complete"
        assert any("fsync failed" in record.message for record in caplog.records)

    def test_temp_creation_error_is_reported_as_permission_error(self, tmp_path):
        """A staging-file allocation failure is reported without creating leftovers."""
        filepath = tmp_path / "allocation.txt"

        with patch.object(
            atomic_write_module.tempfile,
            "mkstemp",
            side_effect=OSError("staging allocation failed"),
        ):
            with pytest.raises(PermissionError, match="Cannot create temp file"):
                atomic_write(filepath, "content")

        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_missing_staging_file_fails_before_publication(self, tmp_path):
        """A staging file disappearing before verification cannot replace the target."""
        filepath = tmp_path / "missing-stage.txt"
        filepath.write_text("original")
        real_exists = Path.exists

        def pretend_stage_is_missing(path):
            if path.name.startswith(f".{filepath.name}.tmp_"):
                return False
            return real_exists(path)

        with patch.object(Path, "exists", new=pretend_stage_is_missing):
            with pytest.raises(OSError, match="does not exist after write"):
                atomic_write(filepath, "replacement")

        assert filepath.read_text() == "original"
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_staging_size_mismatch_rolls_back_before_replace(self, tmp_path):
        """A short staging file is rejected and the existing target is preserved."""
        filepath = tmp_path / "short-stage.txt"
        filepath.write_text("original")
        real_stat = Path.stat

        def report_wrong_size(path, *args, **kwargs):
            stat_result = real_stat(path, *args, **kwargs)
            if path.name.startswith(f".{filepath.name}.tmp_"):
                return SimpleNamespace(st_size=stat_result.st_size + 1)
            return stat_result

        with patch.object(Path, "stat", new=report_wrong_size):
            with pytest.raises(OSError, match="Temp file size mismatch"):
                atomic_write(filepath, "replacement")

        assert filepath.read_text() == "original"
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_publish_error_preserves_target_and_removes_staging(self, tmp_path):
        """A failed replace is surfaced while the old target remains unchanged."""
        filepath = tmp_path / "replace.txt"
        filepath.write_text("original")

        with patch.object(
            atomic_write_module.os,
            "replace",
            side_effect=OSError("publish blocked"),
        ):
            with pytest.raises(OSError, match="publish blocked"):
                atomic_write(filepath, "replacement")

        assert filepath.read_text() == "original"
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_orphan_verification_cleanup_is_best_effort_and_scoped(self, tmp_path):
        """Successful publication also removes an orphan reported for its directory."""
        filepath = tmp_path / "published.txt"
        orphan = tmp_path / ".stale.tmp_for_test.tmp"
        orphan.write_text("stale")

        with patch.object(
            atomic_write_module,
            "_verify_no_orphaned_temps",
            return_value=[orphan],
        ):
            atomic_write(filepath, "new content")

        assert filepath.read_text() == "new content"
        assert not orphan.exists()

    def test_orphan_verification_finds_operation_owned_staging_files(self, tmp_path):
        """A real staging-name match is removed after publication."""
        filepath = tmp_path / "published.txt"
        orphan = tmp_path / ".published.txt.tmp_12345678_stale.tmp"
        orphan.write_text("stale")

        with patch.object(
            atomic_write_module.uuid,
            "uuid4",
            return_value=UUID("12345678-1234-5678-1234-567812345678"),
        ):
            atomic_write(filepath, "new content")

        assert filepath.read_text() == "new content"
        assert not orphan.exists()
        assert list(tmp_path.glob(".published.txt.tmp_*.tmp")) == []


class TestRollbackCleanupFailureModes:
    """Validate rollback context behavior for setup, commit, and cleanup errors."""

    def test_rollback_missing_staging_file_preserves_original_error(self, tmp_path):
        """A staging file removed before commit produces a clear rollback error."""
        filepath = tmp_path / "rollback-missing.txt"

        with pytest.raises(OSError, match="does not exist after context block"):
            with atomic_write_rollback(filepath) as temp_path:
                temp_path.unlink()

        assert not filepath.exists()
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_rollback_publish_failure_preserves_existing_target(self, tmp_path):
        """A rollback-context replace failure leaves the prior target and no stage."""
        filepath = tmp_path / "rollback-publish.txt"
        filepath.write_text("original")

        with patch.object(
            atomic_write_module.os,
            "replace",
            side_effect=OSError("rollback publish blocked"),
        ):
            with pytest.raises(OSError, match="rollback publish blocked"):
                with atomic_write_rollback(filepath) as temp_path:
                    temp_path.write_text("replacement")

        assert filepath.read_text() == "original"
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_rollback_temp_allocation_failure_has_no_orphan(self, tmp_path):
        """Rollback setup failure is translated and cannot strand a temp path."""
        filepath = tmp_path / "rollback-allocation.txt"

        with patch.object(
            atomic_write_module.tempfile,
            "mkstemp",
            side_effect=OSError("no staging space"),
        ):
            with pytest.raises(PermissionError, match="Cannot create temp file"):
                with atomic_write_rollback(filepath):
                    pytest.fail("the rollback context should not yield")

        assert list(tmp_path.glob(_staging_pattern(filepath))) == []

    def test_rollback_descriptor_close_failure_removes_staging(self, tmp_path):
        """Failure preparing the rollback descriptor removes its staging file."""
        filepath = tmp_path / "rollback-close.txt"
        real_close = atomic_write_module.os.close
        descriptor = None

        def fail_close(fd):
            nonlocal descriptor
            descriptor = fd
            raise OSError("descriptor close blocked")

        with patch.object(atomic_write_module.os, "close", new=fail_close):
            with pytest.raises(OSError, match="Failed to prepare rollback temp file"):
                with atomic_write_rollback(filepath):
                    pytest.fail("the rollback context should not yield")

        # The mocked close intentionally leaves the descriptor open so the
        # test can inspect the failure; close it after restoring real behavior.
        assert descriptor is not None
        real_close(descriptor)
        assert list(tmp_path.glob(_staging_pattern(filepath))) == []


class TestOrphanCleanupEdgeCases:
    """Validate permission, listing, and concurrent orphan cleanup behavior."""

    def test_permission_error_reports_failed_file_without_masking_other_cleanup(self, tmp_path):
        """One locked orphan is reported while independent files are removed."""
        blocked = tmp_path / "blocked.tmp"
        removable = tmp_path / "removable.tmp"
        blocked.write_text("locked")
        removable.write_text("remove")
        real_unlink = Path.unlink

        def fail_one(path, missing_ok=False):
            if path == blocked:
                raise PermissionError("file is locked")
            return real_unlink(path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", new=fail_one):
            result = cleanup_orphaned_temp_files(tmp_path, return_details=True)

        assert result["cleaned"] == 1
        assert result["failed"] == 1
        assert any("Permission denied" in error for error in result["errors"])
        assert not removable.exists()
        assert blocked.exists()
        blocked.unlink()

    def test_permission_error_can_be_escalated(self, tmp_path):
        """The strict cleanup option raises after recording a removal failure."""
        blocked = tmp_path / "strict.tmp"
        blocked.write_text("locked")
        real_unlink = Path.unlink

        def fail_unlink(path, missing_ok=False):
            if path == blocked:
                raise PermissionError("file is locked")
            return real_unlink(path, missing_ok=missing_ok)

        try:
            with patch.object(Path, "unlink", new=fail_unlink):
                with pytest.raises(OSError, match="Cleanup failed for 1 files"):
                    cleanup_orphaned_temp_files(
                        tmp_path,
                        return_details=True,
                        raise_on_failure=True,
                    )
        finally:
            blocked.unlink(missing_ok=True)

    def test_listing_permission_error_is_reported_and_can_be_escalated(self, tmp_path):
        """A directory listing failure is observable in both best-effort modes."""
        orphan = tmp_path / "orphan.tmp"
        orphan.write_text("orphan")

        with patch.object(Path, "glob", side_effect=PermissionError("directory locked")):
            result = cleanup_orphaned_temp_files(tmp_path, return_details=True)
        assert result["cleaned"] == 0
        assert result["failed"] == 0
        assert "Permission denied listing" in result["errors"][0]

        with patch.object(Path, "glob", side_effect=PermissionError("directory locked")):
            with pytest.raises(PermissionError, match="Permission denied listing"):
                cleanup_orphaned_temp_files(tmp_path, raise_on_failure=True)

        orphan.unlink()

    def test_cleanup_is_safe_for_two_simultaneous_owners(self, tmp_path):
        """Concurrent cleanup owners converge on an empty directory without errors."""
        for index in range(24):
            (tmp_path / f"concurrent-{index}.tmp").write_text("orphan")

        import threading

        start = threading.Barrier(4)

        def cleanup_from_worker():
            start.wait()
            return cleanup_orphaned_temp_files(tmp_path, return_details=True)

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: cleanup_from_worker(), range(4)))

        assert all(result["failed"] == 0 for result in results)
        assert list(tmp_path.glob("*.tmp")) == []

    def test_missing_directory_and_non_directory_are_explicit(self, tmp_path):
        """Cleanup reports missing paths and rejects a regular file in strict mode."""
        missing = tmp_path / "missing"
        assert cleanup_orphaned_temp_files(missing) == 0
        with pytest.raises(OSError, match="Directory does not exist"):
            cleanup_orphaned_temp_files(missing, raise_on_failure=True)

        regular_file = tmp_path / "not-a-directory"
        regular_file.write_text("data")
        result = cleanup_orphaned_temp_files(regular_file, return_details=True)
        assert result["cleaned"] == 0
        assert result["errors"] == []
        with pytest.raises(NotADirectoryError, match="Path is not a directory"):
            cleanup_orphaned_temp_files(regular_file, raise_on_failure=True)


class TestAtomicAppendEdgeCases:
    """Validate append cleanup, conversion, retry, and failure behavior."""

    def test_existing_text_append_publishes_complete_combined_snapshot(self, tmp_path):
        """Appending to an existing file preserves its prefix and removes stage."""
        filepath = tmp_path / "events.log"
        filepath.write_text("first\n")

        atomic_append(filepath, "second\n")

        assert filepath.read_text() == "first\nsecond\n"
        assert list(tmp_path.glob(".tmp_append_*.tmp_*")) == []

    @pytest.mark.parametrize(
        ("mode", "initial", "addition", "expected"),
        [
            ("a", "text\n", b"bytes\n", "text\nbytes\n"),
            ("ab", b"binary\n", "tail\n", b"binary\ntail\n"),
        ],
    )
    def test_append_normalizes_text_and_binary_inputs(
        self, tmp_path, mode, initial, addition, expected
    ):
        """Text and binary append modes normalize input without partial output."""
        filepath = tmp_path / f"append-{mode}.log"
        filepath.write_bytes(initial if isinstance(initial, bytes) else initial.encode())

        atomic_append(filepath, addition, mode=mode)

        expected_bytes = expected if isinstance(expected, bytes) else expected.encode()
        assert filepath.read_bytes() == expected_bytes

    def test_append_disk_full_preserves_existing_file_and_cleans_stage(self, tmp_path):
        """ENOSPC during append staging never changes the existing log."""
        filepath = tmp_path / "full.log"
        filepath.write_text("before\n")

        with patch.object(
            atomic_write_module,
            "_write_all",
            side_effect=OSError(28, "No space left on device"),
        ):
            with pytest.raises(OSError, match="No space left on device"):
                atomic_append(filepath, "after\n")

        assert filepath.read_text() == "before\n"
        assert list(tmp_path.glob(".tmp_append_*.tmp_*")) == []

    def test_append_retries_transient_new_file_publish(self, tmp_path):
        """A transient append publish failure retries without duplicating content."""
        filepath = tmp_path / "retry.log"
        real_replace = atomic_write_module.os.replace
        attempts = 0

        def fail_once(source, destination):
            nonlocal attempts
            if Path(destination) == filepath and attempts == 0:
                attempts += 1
                raise OSError("temporary publish failure")
            return real_replace(source, destination)

        with patch.object(atomic_write_module.os, "replace", side_effect=fail_once):
            with patch.object(atomic_write_module.time, "sleep") as sleep:
                atomic_append(filepath, "one\n", max_retries=1, initial_delay=0)

        assert attempts == 1
        assert sleep.call_count == 1
        assert filepath.read_text() == "one\n"
        assert list(tmp_path.glob(".tmp_append_*.tmp_*")) == []

    def test_append_validation_failure_does_not_create_staging(self, tmp_path):
        """Rejected append content fails before touching the target directory."""
        filepath = tmp_path / "validated.log"

        with pytest.raises(ValueError, match="Content validation failed"):
            atomic_append(filepath, "invalid", validate_fn=lambda _: False)

        assert not filepath.exists()
        assert list(tmp_path.glob(".tmp_append_*.tmp_*")) == []


def test_end_to_end_failed_transaction_then_startup_cleanup_is_deterministic(tmp_path):
    """A failed transaction plus startup sweep restores the complete cleanup contract."""
    filepath = tmp_path / "state.json"
    stale = tmp_path / "crash-leftover.tmp"
    filepath.write_text('{"state": "old"}')
    stale.write_text("interrupted")

    with pytest.raises(RuntimeError, match="processing failed"):
        with atomic_write_rollback(filepath) as temp_path:
            temp_path.write_text('{"state": "partial"}')
            raise RuntimeError("processing failed")

    result = cleanup_orphaned_temp_files(tmp_path, return_details=True)

    assert result["cleaned"] == 1
    assert result["failed"] == 0
    assert filepath.read_text() == '{"state": "old"}'
    assert list(tmp_path.glob("*.tmp")) == []
