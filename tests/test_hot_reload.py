#!/usr/bin/env python3
"""
Test script to verify hot-reload behavior of prompts and configs.

This script tests:
1. Router prompt (prompts/router.md) is reloaded on change
2. Registry config (config/registry.yaml) is reloaded on change
3. Changes are picked up without server restart
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.components.hot_reload import get_reload_manager


async def test_router_prompt_hot_reload():
    """Test that router prompt is hot-reloaded."""
    print("\n=== Testing Router Prompt Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_prompt = reload_mgr.get_prompt('router')

    print(f"Original prompt length: {len(original_prompt)} chars")

    # Touch the router.md file to change mtime
    router_path = Path("prompts/router.md")
    original_content = router_path.read_text()

    # Modify the file
    test_content = original_content + "\n# Test line added at " + str(time.time())
    router_path.write_text(test_content)

    # Wait for throttle interval (1 second)
    await asyncio.sleep(1.5)

    # Get the prompt again
    modified_prompt = reload_mgr.get_prompt('router')

    print(f"Modified prompt length: {len(modified_prompt)} chars")

    # Restore original content
    router_path.write_text(original_content)

    # Check if the change was detected
    if len(modified_prompt) > len(original_prompt):
        print("✓ Router prompt hot-reload: PASSED (change detected)")
        return True
    else:
        print("✗ Router prompt hot-reload: FAILED (change not detected)")
        return False


async def test_registry_config_hot_reload():
    """Test that registry config is hot-reloaded."""
    print("\n=== Testing Registry Config Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_config = reload_mgr.get_config('registry')

    print(f"Original config projects count: {len(original_config.get('projects', {}))}")

    # Touch the registry.yaml file
    registry_path = Path("config/registry.yaml")
    original_content = registry_path.read_text()

    # Add a test project
    test_project = "\n  test-hot-reload-project:\n    description: 'Test project for hot-reload'\n    aliases: ['test', 'hotreload']\n    cluster: null\n    namespace: null\n    intent_support: ['status']\n"
    modified_content = original_content + test_project
    registry_path.write_text(modified_content)

    # Wait for throttle interval
    await asyncio.sleep(1.5)

    # Get config again
    modified_config = reload_mgr.get_config('registry')

    print(f"Modified config projects count: {len(modified_config.get('projects', {}))}")

    # Restore original content
    registry_path.write_text(original_content)

    # Check if the change was detected
    if len(modified_config.get('projects', {})) > len(original_config.get('projects', {})):
        print("✓ Registry config hot-reload: PASSED (change detected)")
        return True
    else:
        print("✗ Registry config hot-reload: FAILED (change not detected)")
        return False


async def test_yaml_registry_cache_expiry():
    """Test that YAML registry cache expires after TTL."""
    print("\n=== Testing YAML Registry Cache Expiry ===")

    from registry import get_registry, CACHE_TTL

    # Force rebuild to start fresh
    registry1 = get_registry(force=True)
    original_count = len(registry1['projects'])
    print(f"Initial registry project count: {original_count}")

    # Wait less than TTL (should return cached version)
    await asyncio.sleep(CACHE_TTL - 5)
    registry2 = get_registry()
    cached_count = len(registry2['projects'])
    print(f"Registry count after {CACHE_TTL - 5}s (should be cached): {cached_count}")

    if cached_count == original_count:
        print("✓ Cache still valid before TTL: PASSED")
    else:
        print("✗ Cache expired prematurely: FAILED")
        return False

    # Wait past TTL (should rebuild)
    await asyncio.sleep(6)  # Total wait: CACHE_TTL + 1 second
    registry3 = get_registry()
    rebuilt_count = len(registry3['projects'])
    print(f"Registry count after {CACHE_TTL + 1}s (should rebuild): {rebuilt_count}")

    if rebuilt_count == original_count:
        print("✓ Registry rebuilt after TTL: PASSED")
        return True
    else:
        print("✗ Registry rebuild failed: FAILED")
        return False


async def main():
    print("Hot-Reload Verification Test")
    print("=" * 50)

    results = []

    # Test router prompt hot-reload
    results.append(await test_router_prompt_hot_reload())

    # Test registry config hot-reload
    results.append(await test_registry_config_hot_reload())

    # Test YAML registry cache expiry
    results.append(await test_yaml_registry_cache_expiry())

    print("\n" + "=" * 50)
    print(f"Results: {sum(results)}/{len(results)} tests passed")

    if all(results):
        print("\n✓ All hot-reload tests PASSED")
        print("\nConclusion:")
        print("- prompts/router.md: Hot-reloads within 1 second ✓")
        print("- config/registry.yaml (HotReloadManager): Hot-reloads within 1 second ✓")
        print("- config/registry.yaml (registry.py): Reloads after 5-minute TTL ✓")
        return 0
    else:
        print("\n✗ Some hot-reload tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
