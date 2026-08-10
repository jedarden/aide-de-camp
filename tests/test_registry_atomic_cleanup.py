"""Regression tests for atomic registry cleanup and interrupted restoration."""

from pathlib import Path
from unittest.mock import patch

import pytest

import src.utils.atomic_write as atomic_write_module
from tests.helpers import registry_test_helpers as registry_helpers


class TestRegistryAtomicCleanup:
    """Verify registry cleanup remains recoverable across interrupted writes."""

    def test_interrupted_cleanup_preserves_registry_and_allows_retry(
        self, tmp_path, monkeypatch
    ):
        registry_path = tmp_path / "registry.yaml"
        original_content = "projects:\n  demo: old\n"
        modified_content = "projects:\n  demo: changed\n"
        registry_path.write_text(original_content)

        monkeypatch.setattr(registry_helpers, "REGISTRY_PATH", registry_path)
        monkeypatch.setattr(registry_helpers, "_test_registry_backup_path", None)
        registry_helpers.setup_test_registry()
        backup_path = registry_helpers._test_registry_backup_path
        assert backup_path is not None

        registry_path.write_text(modified_content)
        real_replace = atomic_write_module.os.replace

        def interrupt_registry_publish(source, destination):
            if Path(destination) == registry_path:
                raise KeyboardInterrupt("simulated cleanup interruption")
            return real_replace(source, destination)

        with patch.object(
            atomic_write_module.os,
            "replace",
            side_effect=interrupt_registry_publish,
        ):
            with pytest.raises(KeyboardInterrupt, match="cleanup interruption"):
                registry_helpers.cleanup_test_registry()

        assert registry_path.read_text() == modified_content
        assert backup_path.exists()
        assert registry_helpers._test_registry_backup_path == backup_path
        assert list(tmp_path.glob(".registry.yaml.tmp_*.tmp")) == []

        registry_helpers.cleanup_test_registry()

        assert registry_path.read_text() == original_content
        assert not backup_path.exists()
        assert registry_helpers._test_registry_backup_path is None

    def test_interrupted_backup_creation_does_not_expose_partial_backup(
        self, tmp_path, monkeypatch
    ):
        registry_path = tmp_path / "registry.yaml"
        registry_path.write_text("projects:\n  demo: old\n")
        monkeypatch.setattr(registry_helpers, "REGISTRY_PATH", registry_path)
        monkeypatch.setattr(registry_helpers, "_test_registry_backup_path", None)

        def interrupt_backup_publish(source, destination):
            raise KeyboardInterrupt("simulated backup interruption")

        with patch.object(
            atomic_write_module.os,
            "replace",
            side_effect=interrupt_backup_publish,
        ):
            with pytest.raises(KeyboardInterrupt, match="backup interruption"):
                registry_helpers.backup_registry()

        assert registry_path.read_text() == "projects:\n  demo: old\n"
        assert list(tmp_path.glob(".registry.yaml.backup.*.tmp")) == []
        assert list(tmp_path.glob(".registry.yaml.backup.*")) == []
