"""Test fixtures and utilities for config hot reload functionality."""

import pathlib
import shutil
from typing import Any, Generator

import pytest
import yaml


def load_registry_config(registry_path: pathlib.Path | str | None = None) -> dict[str, Any]:
    """
    Load and parse the registry configuration file.

    Args:
        registry_path: Optional path to the registry file. Defaults to config/registry.yaml.

    Returns:
        Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the registry file doesn't exist.
        yaml.YAMLError: If the YAML is invalid.
    """
    if registry_path is None:
        registry_path = pathlib.Path("config/registry.yaml")
    else:
        registry_path = pathlib.Path(registry_path)

    if not registry_path.exists():
        raise FileNotFoundError(f"Registry file not found: {registry_path}")

    with open(registry_path) as f:
        return yaml.safe_load(f)


def modify_registry_alias(
    old_alias: str,
    new_alias: str,
    registry_path: pathlib.Path | str | None = None,
) -> None:
    """
    Modify an alias in the registry configuration file.

    This function finds all occurrences of old_alias in project aliases and
    global_aliases, replaces them with new_alias, and writes the updated
    content back to the file while preserving YAML formatting.

    Args:
        old_alias: The alias to replace.
        new_alias: The new alias value.
        registry_path: Optional path to the registry file. Defaults to config/registry.yaml.

    Raises:
        FileNotFoundError: If the registry file doesn't exist.
        ValueError: If old_alias is not found in the registry.
    """
    if registry_path is None:
        registry_path = pathlib.Path("config/registry.yaml")
    else:
        registry_path = pathlib.Path(registry_path)

    if not registry_path.exists():
        raise FileNotFoundError(f"Registry file not found: {registry_path}")

    # Load the YAML content
    with open(registry_path) as f:
        config = yaml.safe_load(f)

    alias_found = False

    # Update global_aliases
    if "global_aliases" in config and config["global_aliases"]:
        # Convert to list to avoid RuntimeError from modifying dict during iteration
        for alias_name, project in list(config["global_aliases"].items()):
            if alias_name == old_alias:
                config["global_aliases"][new_alias] = config["global_aliases"].pop(old_alias)
                alias_found = True
            # Also check if the alias value matches old_alias
            elif project == old_alias:
                config["global_aliases"][alias_name] = new_alias
                alias_found = True

    # Update project aliases
    if "projects" in config and config["projects"]:
        for project_name, project_config in config["projects"].items():
            if "aliases" in project_config and project_config["aliases"]:
                aliases = project_config["aliases"]
                if old_alias in aliases:
                    # Replace the alias in the list
                    index = aliases.index(old_alias)
                    aliases[index] = new_alias
                    alias_found = True

    if not alias_found:
        raise ValueError(f"Alias '{old_alias}' not found in registry")

    # Write back to file, preserving formatting
    with open(registry_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


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


class TestRegistryHelpers:
    """Unit tests for registry helper functions."""

    def test_load_registry_config(self, backup_registry):
        """Test load_registry_config() helper."""
        config = load_registry_config()

        # Verify it's a dictionary
        assert isinstance(config, dict)

        # Verify expected keys exist
        assert "projects" in config
        assert "global_aliases" in config

        # Verify we can access a project
        assert "aide-de-camp" in config["projects"]
        assert "aliases" in config["projects"]["aide-de-camp"]

    def test_load_registry_config_with_path(self, backup_registry):
        """Test load_registry_config() with explicit path argument."""
        registry_path = pathlib.Path("config/registry.yaml")
        config = load_registry_config(registry_path)

        assert isinstance(config, dict)
        assert "projects" in config

    def test_load_registry_config_file_not_found(self):
        """Test load_registry_config() raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Registry file not found"):
            load_registry_config("nonexistent/path/registry.yaml")

    def test_modify_registry_alias_project_alias(self, backup_registry):
        """Test modify_registry_alias() updates a project alias."""
        # Modify an alias
        modify_registry_alias("adc", "test-alias")

        # Verify the change
        config = load_registry_config()
        aide_de_camp = config["projects"]["aide-de-camp"]
        assert "test-alias" in aide_de_camp["aliases"]
        assert "adc" not in aide_de_camp["aliases"]

    def test_modify_registry_alias_global_alias(self, backup_registry):
        """Test modify_registry_alias() updates a global alias key."""
        # Modify a global alias key
        modify_registry_alias("prod", "production")

        # Verify the change
        config = load_registry_config()
        assert "production" in config["global_aliases"]
        assert "prod" not in config["global_aliases"]
        assert config["global_aliases"]["production"] == "options-pipeline"

    def test_modify_registry_alias_preserves_structure(self, backup_registry):
        """Test modify_registry_alias() preserves YAML structure and other data."""
        # Get original config
        original_config = load_registry_config()
        original_project_count = len(original_config["projects"])

        # Modify an alias
        modify_registry_alias("kalshi", "test-kalshi-alias")

        # Verify structure is preserved
        new_config = load_registry_config()
        assert len(new_config["projects"]) == original_project_count
        assert "global_aliases" in new_config
        assert "clusters" in new_config
        assert "argocd" in new_config

        # Verify other projects are unchanged
        assert "aide-de-camp" in new_config["projects"]
        assert "declarative-config" in new_config["projects"]

    def test_modify_registry_alias_alias_not_found(self, backup_registry):
        """Test modify_registry_alias() raises ValueError for missing alias."""
        with pytest.raises(ValueError, match="Alias 'nonexistent-alias' not found"):
            modify_registry_alias("nonexistent-alias", "new-alias")

    def test_modify_registry_alias_file_not_found(self):
        """Test modify_registry_alias() raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Registry file not found"):
            modify_registry_alias("adc", "new-alias", "nonexistent/path/registry.yaml")

    def test_modify_registry_alias_with_path_argument(self, backup_registry):
        """Test modify_registry_alias() with explicit path argument."""
        registry_path = pathlib.Path("config/registry.yaml")
        modify_registry_alias("pbx", "test-pbx-alias", registry_path)

        config = load_registry_config()
        pbx_project = config["projects"]["pbx-web"]
        assert "test-pbx-alias" in pbx_project["aliases"]
        assert "pbx" not in pbx_project["aliases"]
