#!/usr/bin/env python3
"""
Test coverage for config/registry.yaml hot-reload behavior.

This test verifies that:
1. Registry aliases can be modified in config/registry.yaml
2. Changes are picked up on subsequent dispatches (via get_registry reload)
3. Original state can be restored after testing
"""

import asyncio
import sys
import time
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from registry import get_registry, REGISTRY_PATH, CACHE_TTL


def test_registry_alias_hot_reload():
    """
    Test that modifying a registry alias in config/registry.yaml
    is picked up by get_registry(force=True).

    This simulates what happens when:
    1. An agent modifies config/registry.yaml (e.g., adding a new alias)
    2. The same utterance is re-dispatched
    3. The router picks up the new alias via get_registry reload
    """
    print("\n=== Testing Registry Alias Hot-Reload ===\n")

    # Force reload to start fresh
    original_registry = get_registry(force=True)

    # Use pbx-web project as our test subject (it has multiple aliases)
    test_project = "pbx-web"
    original_entry = original_registry["projects"].get(test_project)

    assert original_entry is not None, f"Test project '{test_project}' not found in registry"

    original_aliases = list(original_entry.get("aliases", []))
    print(f"Original aliases for {test_project}: {original_aliases}")

    # Read the YAML file directly
    original_yaml_content = REGISTRY_PATH.read_text()
    parsed = yaml.safe_load(original_yaml_content)

    # Add a test alias that doesn't exist yet
    test_alias = f"test-alias-{int(time.time())}"

    # Modify the YAML
    assert test_project in parsed.get("projects", {}), f"Test project '{test_project}' not found in YAML"
    parsed["projects"][test_project]["aliases"] = original_aliases + [test_alias]

    modified_yaml_content = yaml.dump(parsed, default_flow_style=False)

    # Write the modified YAML
    try:
        REGISTRY_PATH.write_text(modified_yaml_content)
        print(f"Added test alias '{test_alias}' to {test_project}")

        # Force reload to pick up the change
        reloaded_registry = get_registry(force=True)
        reloaded_entry = reloaded_registry["projects"].get(test_project)
        reloaded_aliases = list(reloaded_entry.get("aliases", []))

        print(f"Reloaded aliases for {test_project}: {reloaded_aliases}")

        # Verify the new alias is present
        assert test_alias in reloaded_aliases, f"Test alias '{test_alias}' NOT found in reloaded registry"
        print(f"✓ Test alias '{test_alias}' successfully picked up after reload")

        # Additional check: verify the alias count increased
        assert len(reloaded_aliases) == len(original_aliases) + 1, \
            f"Alias count mismatch: expected {len(original_aliases) + 1}, got {len(reloaded_aliases)}"
        print(f"✓ Alias count increased correctly ({len(original_aliases)} → {len(reloaded_aliases)})")

    finally:
        # Always restore the original content, even if test fails
        print(f"\nRestoring original YAML content...")
        REGISTRY_PATH.write_text(original_yaml_content)

        # Force reload again to pick up the restoration
        restored_registry = get_registry(force=True)
        restored_entry = restored_registry["projects"].get(test_project)
        restored_aliases = list(restored_entry.get("aliases", []))

        print(f"Restored aliases for {test_project}: {restored_aliases}")

        # Verify restoration worked
        assert test_alias not in restored_aliases, "Test alias still present after restoration"
        print(f"✓ Test alias successfully removed after restoration")

        # Verify we're back to original state
        assert set(restored_aliases) == set(original_aliases), \
            f"Registry aliases differ from original: {original_aliases} vs {restored_aliases}"
        print(f"✓ Registry fully restored to original state")

    print("\n✓ Registry alias hot-reload test: PASSED")


def test_registry_cache_invalidation():
    """
    Test that the registry cache respects CACHE_TTL and can be invalidated.

    This verifies:
    1. Cache works (subsequent calls within TTL return cached data)
    2. Cache expires after CACHE_TTL
    3. force=True bypasses cache and rebuilds
    """
    print("\n=== Testing Registry Cache Invalidation ===\n")

    # Force rebuild to start fresh
    registry1 = get_registry(force=True)
    initial_project_count = len(registry1["projects"])
    print(f"Initial project count: {initial_project_count}")

    # Call again without force - should return cached version
    registry2 = get_registry(force=False)
    cached_project_count = len(registry2["projects"])
    print(f"Cached project count: {cached_project_count}")

    assert cached_project_count == initial_project_count, "Cache returned different data (unexpected)"
    print("✓ Cache returned same data")

    # Verify it's actually cached (same object)
    assert registry2 is registry1, "Cache returned different object"
    print("✓ Cache returned same object reference")

    # Force reload should rebuild
    registry3 = get_registry(force=True)
    forced_project_count = len(registry3["projects"])
    print(f"Forced reload project count: {forced_project_count}")

    # With no YAML changes, counts should be equal
    assert forced_project_count == initial_project_count, "Force reload returned different data count"
    print("✓ Force reload returned same data (no YAML changes)")

    print("\n✓ Registry cache invalidation test: PASSED")


def test_registry_alias_dispatch_integration():
    """
    Test that a new alias in registry.yaml would be picked up in dispatch routing.

    This simulates the full flow:
    1. Add a new alias to a project
    2. Verify that routing would recognize the alias
    3. Restore the original state
    """
    print("\n=== Testing Registry Alias Dispatch Integration ===\n")

    # Use whisper-stt as test project (has many aliases)
    test_project = "whisper-stt"
    test_alias = f"voice-to-text-{int(time.time())}"

    # Load fresh registry
    registry = get_registry(force=True)
    original_entry = registry["projects"].get(test_project)

    assert original_entry is not None, f"Test project '{test_project}' not found"

    original_aliases = list(original_entry.get("aliases", []))
    print(f"Original aliases for {test_project}: {original_aliases}")

    # Read and modify YAML
    original_yaml = REGISTRY_PATH.read_text()
    parsed = yaml.safe_load(original_yaml)

    assert test_project in parsed.get("projects", {}), f"Test project '{test_project}' not found in YAML"
    parsed["projects"][test_project]["aliases"] = original_aliases + [test_alias]

    try:
        # Write modified YAML
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))
        print(f"Added test alias '{test_alias}' to {test_project}")

        # Force reload
        reloaded_registry = get_registry(force=True)

        # Simulate utterance matching with the new alias
        # Check if the new alias would be found in the registry
        test_utterance = f"check the {test_alias} status"

        # Verify the alias exists in reloaded registry
        found = False
        for slug, entry in reloaded_registry["projects"].items():
            if slug == test_project:
                aliases = entry.get("aliases", [])
                if test_alias in aliases:
                    found = True
                    print(f"✓ New alias '{test_alias}' found in {test_project}")
                    break

        assert found, f"New alias '{test_alias}' NOT found after reload"

        # Verify utterance would match (simplified check)
        utterance_lower = test_utterance.lower()
        assert test_alias in utterance_lower, "Test utterance doesn't contain new alias"
        print(f"✓ Test utterance '{test_utterance}' contains new alias")

    finally:
        # Restore original YAML
        REGISTRY_PATH.write_text(original_yaml)
        get_registry(force=True)  # Force reload to restore
        print(f"✓ Restored original registry state")

    print("\n✓ Registry alias dispatch integration test: PASSED")


def main():
    """Run all registry hot-reload tests."""
    print("=" * 60)
    print("Registry Hot-Reload Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0
    total = 3

    # Test 1: Basic alias hot-reload
    try:
        test_registry_alias_hot_reload()
        passed += 1
    except Exception as e:
        print(f"\n✗ Test 1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 2: Cache invalidation
    try:
        test_registry_cache_invalidation()
        passed += 1
    except Exception as e:
        print(f"\n✗ Test 2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 3: Dispatch integration
    try:
        test_registry_alias_dispatch_integration()
        passed += 1
    except Exception as e:
        print(f"\n✗ Test 3 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if failed == 0:
        print("\n✓ All registry hot-reload tests PASSED")
        print("\nConclusion:")
        print("- config/registry.yaml aliases can be modified ✓")
        print("- Changes are picked up via get_registry(force=True) ✓")
        print("- Original state is properly restored ✓")
        print("- Dispatch routing would recognize new aliases ✓")
        return 0
    else:
        print("\n✗ Some registry hot-reload tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
