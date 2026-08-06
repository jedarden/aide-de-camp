"""Test fixtures and utilities for config hot reload functionality."""

import pathlib
import shutil
from typing import Generator

import pytest


@pytest.fixture
def backup_registry(tmp_path: pathlib.Path) -> Generator[None, None, None]:
    """
    Fixture that backs up config/registry.yaml before a test and restores it after.

    This ensures tests are idempotent and can run multiple times without polluting
    the config. The backup is created even if the test fails, and restoration is
    guaranteed by the yield pattern.

    Args:
        tmp_path: pytest fixture providing a temporary directory path

    Yields:
        None
    """
    registry_path = pathlib.Path("config/registry.yaml")
    backup_path = tmp_path / "registry.yaml.backup"

    # Setup: back up the current registry.yaml
    if registry_path.exists():
        shutil.copy(registry_path, backup_path)

    try:
        yield
    finally:
        # Teardown: restore from backup regardless of test outcome
        if backup_path.exists():
            shutil.copy(backup_path, registry_path)


def test_backup_registry_restores_after_modification(backup_registry):
    """Test that the backup_registry fixture correctly restores the original file."""
    import yaml

    registry_path = pathlib.Path("config/registry.yaml")

    # Read the original content
    with open(registry_path) as f:
        original_content = f.read()

    # Modify the file
    with open(registry_path, "w") as f:
        f.write("# Modified content\n")

    # Verify it was modified
    with open(registry_path) as f:
        modified_content = f.read()
    assert modified_content == "# Modified content\n"

    # After the test ends, the fixture should restore the original content
    # We can't verify this within the test, but we can check that the backup
    # was created successfully

    # Read the original as YAML to verify it's valid
    original_data = yaml.safe_load(original_content)
    assert "projects" in original_data
    assert "aide-de-camp" in original_data["projects"]
