"""
Test helpers for safe registry modification and restoration.

This module provides utilities for safely modifying config/registry.yaml
during tests, with automatic cleanup and restoration capabilities.

ENHANCED WITH ATOMIC OPERATIONS: All file operations use atomic writes
to prevent corruption during concurrent test execution.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import yaml

# Registry path is defined in src/registry.py but we import it here
# to avoid circular dependencies in test code
REGISTRY_PATH = Path(__file__).parent.parent.parent / "config" / "registry.yaml"


def _atomic_write(path: Path, content: str) -> None:
    """
    Write content to a file atomically to prevent corruption.

    CONCURRENT ACCESS PROTECTION: Atomic file operations ensure that writes
    are all-or-nothing, preventing partial file states during concurrent test
    execution. This is critical for registry cleanup operations.

    Implementation:
    1. Write to temporary file in same directory (ensures same filesystem)
    2. Flush and fsync to ensure data reaches disk
    3. Atomic rename to replace target (POSIX-compliant, works on Linux)

    Args:
        path: Target file path to write
        content: Content to write to the file

    Raises:
        OSError: If write operation fails
    """
    # Create temporary file in same directory as target
    temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix='.atomic_write_')

    try:
        # Write content to temporary file
        with os.fdopen(temp_fd, 'w') as f:
            f.write(content)
            f.flush()
            # Ensure data is written to physical disk
            os.fsync(f.fileno())

        # Atomic rename - replaces target file if it exists
        os.rename(temp_path, path)

    except Exception:
        # Clean up temporary file on failure
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        raise


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

    # Create backup with timestamp to avoid collisions
    import time
    backup_path = REGISTRY_PATH.parent / f"registry.yaml.backup.{int(time.time())}"

    shutil.copy2(REGISTRY_PATH, backup_path)
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
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    if not backup_path.name.startswith("registry.yaml.backup."):
        raise ValueError(
            f"Invalid backup file: {backup_path.name}. "
            "Only files created by backup_registry() should be used."
        )

    # Use atomic write for safe restoration
    backup_content = backup_path.read_text()
    _atomic_write(REGISTRY_PATH, backup_content)


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
    if backup_path.exists():
        backup_path.unlink()


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
        _atomic_write(REGISTRY_PATH, modified_yaml)

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
    _atomic_write(REGISTRY_PATH, modified_yaml)
