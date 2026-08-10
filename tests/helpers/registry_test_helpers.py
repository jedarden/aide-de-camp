"""
Test helpers for safe registry modification and restoration.

This module provides utilities for safely modifying config/registry.yaml
during tests, with automatic cleanup and restoration capabilities.

ENHANCED WITH ATOMIC OPERATIONS: All file operations use centralized atomic writes
to prevent corruption during concurrent test execution.
"""

import threading
import uuid
from pathlib import Path
from typing import Optional

import yaml

from src.utils.atomic_write import atomic_write

# Registry path is defined in src/registry.py but we import it here
# to avoid circular dependencies in test code
REGISTRY_PATH = Path(__file__).parent.parent.parent / "config" / "registry.yaml"
_registry_cleanup_lock = threading.RLock()


def backup_registry() -> Path:
    """
    Create a backup of the current registry.yaml file.

    Returns:
        Path: The path to the backup file

    Example:
        >>> backup_path = backup_registry()
        >>> # ... modify registry.yaml ...
        >>> restore_registry(backup_path)
    """
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry file not found: {REGISTRY_PATH}")

    # Include a UUID rather than a timestamp so simultaneous test owners never
    # publish to the same backup path.
    backup_path = REGISTRY_PATH.parent / f"registry.yaml.backup.{uuid.uuid4().hex}"

    # Publish the complete backup atomically so cleanup never reads a partial copy.
    original_content = REGISTRY_PATH.read_text()
    atomic_write(backup_path, original_content)
    return backup_path


def restore_registry(backup_path: Path) -> None:
    """
    Restore registry.yaml from a backup file using atomic operations.

    CONCURRENT ACCESS PROTECTION: Uses atomic file operations to ensure that
    restoration is all-or-nothing, preventing partial file states during
    concurrent test execution.

    Args:
        backup_path: Path to the backup file created by backup_registry()

    Example:
        >>> backup_path = backup_registry()
        >>> # ... modify registry.yaml ...
        >>> restore_registry(backup_path)
    """
    if not backup_path.name.startswith("registry.yaml.backup."):
        raise ValueError(
            f"Invalid backup file: {backup_path.name}. "
            "Only files created by backup_registry() should be used."
        )

    # Read the complete backup and publish restoration with os.replace via
    # atomic_write.  Avoid an exists-then-read check: another cleanup owner can
    # remove the backup between those two operations.
    try:
        backup_content = backup_path.read_text()
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Backup file not found: {backup_path}") from error
    atomic_write(REGISTRY_PATH, backup_content)


def cleanup_backup(backup_path: Path) -> None:
    """
    Remove a backup file created by backup_registry().

    Args:
        backup_path: Path to the backup file

    Example:
        >>> backup_path = backup_registry()
        >>> try:
        >>>     # ... test code ...
        >>> finally:
        >>>     restore_registry(backup_path)
        >>>     cleanup_backup(backup_path)
    """
    # missing_ok makes cleanup idempotent when another owner wins the unlink
    # race.  The unlink itself is the atomic cleanup operation.
    backup_path.unlink(missing_ok=True)


class RegistryModificationContext:
    """
    Context manager for safe registry modification with automatic restoration.

    Example:
        >>> with RegistryModificationContext() as ctx:
        >>>     # Modify registry.yaml
        >>>     ctx.add_alias("pbx-web", "test-alias")
        >>>     # Registry is automatically restored on exit
    """

    def __init__(self, auto_cleanup: bool = True):
        """
        Args:
            auto_cleanup: If True, removes backup file after restoration
        """
        self.auto_cleanup = auto_cleanup
        self.backup_path: Optional[Path] = None
        self._yaml_content: Optional[str] = None
        self._parsed: Optional[dict] = None

    def __enter__(self):
        """Create backup and load current registry content."""
        self.backup_path = backup_registry()
        self._yaml_content = REGISTRY_PATH.read_text()
        self._parsed = yaml.safe_load(self._yaml_content)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore registry and optionally cleanup backup."""
        if self.backup_path:
            restore_registry(self.backup_path)
            if self.auto_cleanup:
                cleanup_backup(self.backup_path)
        return False  # Don't suppress exceptions

    @property
    def projects(self) -> dict:
        """Get projects section from registry."""
        if self._parsed is None:
            raise RuntimeError("Context manager not entered. Use 'with RegistryModificationContext()'")
        return self._parsed.get("projects", {})

    @property
    def clusters(self) -> dict:
        """Get clusters section from registry."""
        if self._parsed is None:
            raise RuntimeError("Context manager not entered. Use 'with RegistryModificationContext()'")
        return self._parsed.get("clusters", {})

    def add_alias(self, project_slug: str, alias: str) -> None:
        """
        Add an alias to a project.

        Args:
            project_slug: Project slug (e.g., "pbx-web")
            alias: New alias to add
        """
        if project_slug not in self.projects:
            raise ValueError(f"Project '{project_slug}' not found in registry")

        project = self.projects[project_slug]
        if "aliases" not in project:
            project["aliases"] = []

        if alias not in project["aliases"]:
            project["aliases"].append(alias)

        self._write()

    def remove_alias(self, project_slug: str, alias: str) -> None:
        """
        Remove an alias from a project.

        Args:
            project_slug: Project slug (e.g., "pbx-web")
            alias: Alias to remove
        """
        if project_slug not in self.projects:
            raise ValueError(f"Project '{project_slug}' not found in registry")

        project = self.projects[project_slug]
        if "aliases" in project and alias in project["aliases"]:
            project["aliases"].remove(alias)

        self._write()

    def _write(self) -> None:
        """
        Write modified content to registry.yaml using atomic operations.

        CONCURRENT ACCESS PROTECTION: Uses atomic file operations to ensure that
        writes are all-or-nothing, preventing partial file states during
        concurrent test execution.
        """
        if self._parsed is None:
            raise RuntimeError("Context manager not entered")

        modified_yaml = yaml.dump(self._parsed, default_flow_style=False)
        atomic_write(REGISTRY_PATH, modified_yaml)

        # Update cached content
        self._yaml_content = modified_yaml


def get_registry_content() -> dict:
    """
    Read and parse the current registry.yaml content.

    Returns:
        Parsed registry as a dictionary
    """
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry file not found: {REGISTRY_PATH}")

    content = REGISTRY_PATH.read_text()
    return yaml.safe_load(content)


def set_registry_content(content: dict) -> None:
    """
    Write new content to registry.yaml using atomic operations.

    CONCURRENT ACCESS PROTECTION: Uses atomic file operations to ensure that
    writes are all-or-nothing, preventing partial file states during
    concurrent test execution.

    Args:
        content: Dictionary to write as YAML

    Example:
        >>> original = get_registry_content()
        >>> try:
        >>>     modified = original.copy()
        >>>     modified["projects"]["new-project"] = {...}
        >>>     set_registry_content(modified)
        >>> finally:
        >>>     set_registry_content(original)
    """
    modified_yaml = yaml.dump(content, default_flow_style=False)
    atomic_write(REGISTRY_PATH, modified_yaml)


# Global tracking for test registry setup/cleanup
_test_registry_backup_path: Optional[Path] = None


def setup_test_registry() -> None:
    """
    Set up a test registry by creating a backup of the current registry.

    This function is called at the beginning of test contexts to ensure
    the original registry can be restored after tests complete.

    CONCURRENT ACCESS PROTECTION: Uses atomic file operations to ensure that
    backup creation is all-or-nothing, preventing partial file states during
    concurrent test execution.

    Raises:
        FileNotFoundError: If registry file doesn't exist

    Example:
        >>> setup_test_registry()
        >>> # ... modify registry for tests ...
        >>> cleanup_test_registry()
    """
    global _test_registry_backup_path

    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry file not found: {REGISTRY_PATH}")

    with _registry_cleanup_lock:
        # Create backup using an atomic write operation.  Publish the complete
        # backup before exposing it to cleanup.
        backup_path = REGISTRY_PATH.parent / f"registry.yaml.backup.{uuid.uuid4().hex}"
        original_content = REGISTRY_PATH.read_text()
        atomic_write(backup_path, original_content)
        _test_registry_backup_path = backup_path


def cleanup_test_registry() -> None:
    """
    Clean up test registry by restoring from backup and removing backup file.

    This function is called at the end of test contexts (usually in finally blocks)
    to ensure the original registry is restored even if tests fail.

    CONCURRENT ACCESS PROTECTION: Uses atomic file operations to ensure that
    restoration is all-or-nothing, preventing partial file states during
    concurrent test execution.

    Raises:
        FileNotFoundError: If backup file doesn't exist

    Example:
        >>> setup_test_registry()
        >>> try:
        >>>     # ... modify registry for tests ...
        >>> finally:
        >>>     cleanup_test_registry()
    """
    global _test_registry_backup_path

    with _registry_cleanup_lock:
        if _test_registry_backup_path is None:
            # No backup was created, nothing to cleanup
            return

        backup_path = _test_registry_backup_path
        try:
            backup_content = backup_path.read_text()
        except FileNotFoundError as error:
            raise FileNotFoundError(f"Backup file not found: {backup_path}") from error

        # Restore original registry using atomic write.  If publishing fails,
        # ownership remains recorded so cleanup can be retried safely.
        atomic_write(REGISTRY_PATH, backup_content)

        # Cleanup is idempotent if another owner removed the backup.  A real
        # permission/filesystem error still leaves ownership recorded for a
        # later retry, preserving the existing failure semantics.
        backup_path.unlink(missing_ok=True)
        _test_registry_backup_path = None
