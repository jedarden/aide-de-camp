#!/usr/bin/env python3
"""
Test suite demonstrating the new registry hot-reload test infrastructure.

This shows how to use the new helper functions and pytest fixtures for safe
registry modification during tests.
"""

import sys
from pathlib import Path

import pytest
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from registry import get_registry, REGISTRY_PATH

from tests.helpers.registry_test_helpers import (
    backup_registry,
    restore_registry,
    cleanup_backup,
    RegistryModificationContext,
    get_registry_content,
    set_registry_content,
)


class TestRegistryHelpers:
    """Test suite for registry helper functions."""

    def test_backup_and_restore(self):
        """Test basic backup and restore functionality."""
        print("\n=== Testing backup_registry() and restore_registry() ===\n")

        # Get original content
        original_content = REGISTRY_PATH.read_text()
        print("✓ Read original registry content")

        # Create backup
        backup_path = backup_registry()
        print(f"✓ Backup created at: {backup_path.name}")

        assert backup_path.exists(), "Backup file was not created"
        assert backup_path.parent == REGISTRY_PATH.parent, "Backup in wrong directory"
        assert backup_path.name.startswith("registry.yaml.backup."), "Backup has wrong name"

        # Modify registry
        modified_content = original_content.replace("# Add test comment", "")
        REGISTRY_PATH.write_text(modified_content)
        print("✓ Modified registry content")

        # Restore from backup
        restore_registry(backup_path)
        restored_content = REGISTRY_PATH.read_text()
        print("✓ Restored from backup")

        assert restored_content == original_content, "Content not properly restored"
        print("✓ Content matches original")

        # Cleanup
        cleanup_backup(backup_path)
        assert not backup_path.exists(), "Backup file not cleaned up"
        print("✓ Backup cleaned up")

        print("\n✓ backup_registry() and restore_registry() test PASSED\n")

    def test_context_manager(self):
        """Test RegistryModificationContext context manager."""
        print("\n=== Testing RegistryModificationContext ===\n")

        test_project = "pbx-web"
        test_alias = "ctx-test-alias"

        # Get original aliases
        original_registry = get_registry(force=True)
        original_entry = original_registry["projects"].get(test_project)
        original_aliases = list(original_entry.get("aliases", []))
        print(f"Original aliases: {original_aliases}")

        # Use context manager
        with RegistryModificationContext() as ctx:
            print("✓ Entered context manager")

            # Add alias
            ctx.add_alias(test_project, test_alias)
            print(f"✓ Added alias '{test_alias}' to {test_project}")

            # Force reload to pick up change
            modified_registry = get_registry(force=True)
            modified_entry = modified_registry["projects"].get(test_project)
            modified_aliases = list(modified_entry.get("aliases", []))

            assert test_alias in modified_aliases, f"Alias '{test_alias}' not in modified registry"
            print(f"✓ Alias '{test_alias}' found in modified registry")

        # Context manager should have restored on exit
        restored_registry = get_registry(force=True)
        restored_entry = restored_registry["projects"].get(test_project)
        restored_aliases = list(restored_entry.get("aliases", []))

        assert test_alias not in restored_aliases, f"Alias '{test_alias}' still in registry after context exit"
        assert set(restored_aliases) == set(original_aliases), "Aliases not restored to original"
        print(f"✓ Registry restored to original state")

        print("\n✓ RegistryModificationContext test PASSED\n")

    def test_get_and_set_content(self):
        """Test get_registry_content and set_registry_content functions."""
        print("\n=== Testing get_registry_content() and set_registry_content() ===\n")

        # Get original content
        original = get_registry_content()
        print(f"✓ Read registry with {len(original.get('projects', {}))} projects")

        # Modify content
        modified = original.copy()
        test_project = "declarative-config"
        if test_project in modified.get("projects", {}):
            modified["projects"][test_project]["description"] = "Test description"
            print(f"✓ Modified description for {test_project}")

            # Set modified content
            set_registry_content(modified)
            print("✓ Wrote modified content")

            # Verify modification
            current = get_registry_content()
            assert current["projects"][test_project]["description"] == "Test description", "Modification not applied"
            print("✓ Modification verified")

            # Restore original
            set_registry_content(original)
            print("✓ Restored original content")

        print("\n✓ get_registry_content() and set_registry_content() test PASSED\n")

    def test_cleanup_safety(self):
        """Test that cleanup only removes backup files."""
        print("\n=== Testing cleanup safety ===\n")

        backup = backup_registry()
        print(f"✓ Created backup: {backup.name}")

        # Cleanup should work
        cleanup_backup(backup)
        assert not backup.exists(), "Backup not cleaned up"
        print("✓ Backup cleaned up successfully")

        # Cleanup on non-existent file should be safe
        cleanup_backup(backup)  # Should not raise
        print("✓ Cleanup of non-existent file is safe")

        print("\n✓ cleanup safety test PASSED\n")


class TestPytestFixtures:
    """Test suite demonstrating pytest fixture usage."""

    def test_registry_backup_path_fixture(self, registry_backup_path):
        """
        Demonstrate registry_backup_path fixture usage.

        The fixture automatically backs up before the test
        and restores after, even if the test fails.
        """
        print("\n=== Testing registry_backup_path fixture ===\n")

        # Modify registry by adding a project alias (this will be picked up)
        original = get_registry(force=True)
        test_project = "declarative-config"
        original_entry = original["projects"].get(test_project)
        original_aliases = list(original_entry.get("aliases", []))
        print(f"Original aliases: {original_aliases}")

        # Modify YAML directly to add a new alias
        yaml_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(yaml_content)
        test_alias = "fixture-backup-test-alias"
        parsed["projects"][test_project]["aliases"] = original_aliases + [test_alias]
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))
        print(f"✓ Added alias '{test_alias}' to {test_project}")

        # Force reload to see change
        modified = get_registry(force=True)
        modified_entry = modified["projects"].get(test_project)
        modified_aliases = list(modified_entry.get("aliases", []))

        assert test_alias in modified_aliases, f"Alias '{test_alias}' not picked up"
        print(f"✓ Alias '{test_alias}' picked up by registry")

        # Test cleanup - fixture will restore automatically
        print("✓ Test complete - fixture will restore registry")

        print("\n✓ registry_backup_path fixture test PASSED\n")

    def test_registry_context_fixture(self, registry_context):
        """
        Demonstrate registry_context fixture usage.

        The fixture provides a context manager for safe modifications.
        """
        print("\n=== Testing registry_context fixture ===\n")

        test_project = "whisper-stt"
        test_alias = "fixture-test-alias"

        # Get original state
        original = get_registry(force=True)
        original_entry = original["projects"].get(test_project)
        original_aliases = list(original_entry.get("aliases", []))
        print(f"Original aliases: {original_aliases}")

        # Use context to add alias
        with registry_context as ctx:
            ctx.add_alias(test_project, test_alias)
            print(f"✓ Added alias '{test_alias}' to {test_project}")

            # Force reload to see change
            modified = get_registry(force=True)
            modified_entry = modified["projects"].get(test_project)
            modified_aliases = list(modified_entry.get("aliases", []))

            assert test_alias in modified_aliases, f"Alias '{test_alias}' not found"
            print(f"✓ Alias '{test_alias}' found in modified registry")

        # Context automatically restores on exit
        restored = get_registry(force=True)
        restored_entry = restored["projects"].get(test_project)
        restored_aliases = list(restored_entry.get("aliases", []))

        assert test_alias not in restored_aliases, f"Alias '{test_alias}' still present"
        print("✓ Registry automatically restored")

        print("\n✓ registry_context fixture test PASSED\n")


def main():
    """Run all tests if executed directly."""
    print("=" * 60)
    print("Registry Hot-Reload Infrastructure Test Suite")
    print("=" * 60)

    # Run helper tests
    helper_tests = TestRegistryHelpers()
    helper_tests.test_backup_and_restore()
    helper_tests.test_context_manager()
    helper_tests.test_get_and_set_content()
    helper_tests.test_cleanup_safety()

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED")
    print("=" * 60)

    print("\nNew infrastructure provides:")
    print("1. backup_registry() - Create timestamped backup")
    print("2. restore_registry() - Restore from backup")
    print("3. cleanup_backup() - Remove backup file")
    print("4. RegistryModificationContext - Context manager for auto-restore")
    print("5. get_registry_content() / set_registry_content() - Direct content access")
    print("6. pytest fixtures: registry_backup_path, registry_context")

    return 0


if __name__ == "__main__":
    sys.exit(main())
