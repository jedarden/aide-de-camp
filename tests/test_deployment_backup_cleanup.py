"""Failure-path tests for deployment backup retention cleanup."""

from pathlib import Path
from unittest.mock import patch

import persist_whisper_stt_deployment as deployment


def test_backup_retention_restores_claim_when_delete_fails(tmp_path):
    """A failed quarantine delete must not strand or lose the old backup."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old_backup = backup_dir / "state_backup_old.json"
    old_backup.write_text("recoverable")

    real_unlink = Path.unlink

    def fail_quarantined_unlink(path, missing_ok=False):
        if path.name.startswith(".deleting_"):
            raise PermissionError("simulated delete failure")
        return real_unlink(path, missing_ok=missing_ok)

    with patch.object(Path, "unlink", new=fail_quarantined_unlink):
        deployment.cleanup_old_backups(backup_dir, "state", keep_count=0)

    assert old_backup.read_text() == "recoverable"
    assert list(backup_dir.glob(".deleting_*.tmp")) == []


def test_backup_retention_success_removes_quarantine_marker(tmp_path):
    """Successful retention cleanup leaves neither the backup nor marker."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    old_backup = backup_dir / "state_backup_old.json"
    old_backup.write_text("obsolete")

    deployment.cleanup_old_backups(backup_dir, "state", keep_count=0)

    assert not old_backup.exists()
    assert list(backup_dir.glob(".deleting_*.tmp")) == []
