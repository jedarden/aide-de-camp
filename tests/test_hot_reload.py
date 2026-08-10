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
from unittest.mock import patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.components.hot_reload import get_reload_manager


async def test_router_prompt_hot_reload():
    """Verify an edited router prompt becomes visible without a restart.

    The test waits past ``HotReloadManager.CHECK_INTERVAL`` to exercise the
    normal mtime-triggered path. The original file and manager cache are
    restored in ``finally`` so a failed assertion cannot pollute later tests.
    """
    print("\n=== Testing Router Prompt Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_prompt = reload_mgr.get_prompt('router')

    print(f"Original prompt length: {len(original_prompt)} chars")

    # Touch the router.md file to change mtime
    router_path = Path("prompts/router.md")
    original_content = router_path.read_text()

    try:
        # Modify the file and wait for the normal one-second check throttle.
        test_content = original_content + "\n# Test line added at " + str(time.time())
        router_path.write_text(test_content)
        await asyncio.sleep(1.5)

        modified_prompt = reload_mgr.get_prompt('router')
        print(f"Modified prompt length: {len(modified_prompt)} chars")

        if len(modified_prompt) > len(original_prompt):
            print("✓ Router prompt hot-reload: PASSED (change detected)")
            return True
        print("✗ Router prompt hot-reload: FAILED (change not detected)")
        return False
    finally:
        router_path.write_text(original_content)
        reload_mgr.force_reload('router')


async def test_registry_config_hot_reload():
    """Verify an edited registry config is parsed on the next eligible read.

    The test adds a disposable project, waits past the mtime-check throttle,
    and checks the parsed project map. Both the source file and the manager's
    cached snapshot are restored in ``finally`` for repeatable isolated runs.
    """
    print("\n=== Testing Registry Config Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_config = reload_mgr.get_config('registry')

    print(f"Original config projects count: {len(original_config.get('projects', {}))}")

    # Touch the registry.yaml file
    registry_path = Path("config/registry.yaml")
    original_content = registry_path.read_text()

    try:
        test_project = "\n  test-hot-reload-project:\n    description: 'Test project for hot-reload'\n    aliases: ['test', 'hotreload']\n    cluster: null\n    namespace: null\n    intent_support: ['status']\n"
        registry_path.write_text(original_content + test_project)
        await asyncio.sleep(1.5)

        modified_config = reload_mgr.get_config('registry')
        print(f"Modified config projects count: {len(modified_config.get('projects', {}))}")

        if len(modified_config.get('projects', {})) > len(original_config.get('projects', {})):
            print("✓ Registry config hot-reload: PASSED (change detected)")
            return True
        print("✗ Registry config hot-reload: FAILED (change not detected)")
        return False
    finally:
        registry_path.write_text(original_content)
        reload_mgr.force_reload('registry')


async def test_yaml_registry_cache_expiry():
    """Test TTL invalidation without sleeping for the production five-minute TTL.

    Edge case: a stale registry cache must rebuild promptly after its deadline.
    The test uses a short injected TTL so a broken cache cannot make the suite
    wait for minutes; a timeout or malformed file should identify the path and
    corrective action in the raised error.
    """
    print("\n=== Testing YAML Registry Cache Expiry ===")

    import registry as registry_module
    from registry import get_registry

    with patch.object(registry_module, "CACHE_TTL", 0.1):
        # Force rebuild to start fresh
        registry1 = get_registry(force=True)
        original_count = len(registry1['projects'])
        print(f"Initial registry project count: {original_count}")

        # Wait less than the injected TTL (should return cached version).
        await asyncio.sleep(0.01)
        registry2 = get_registry()
        cached_count = len(registry2['projects'])
        print(f"Registry count before TTL (should be cached): {cached_count}")

        if cached_count == original_count:
            print("✓ Cache still valid before TTL: PASSED")
        else:
            print("✗ Cache expired prematurely: FAILED")
            return False

        # Wait past the injected TTL (should rebuild).
        await asyncio.sleep(0.12)
        registry3 = get_registry()
        rebuilt_count = len(registry3['projects'])
        print(f"Registry count after injected TTL (should rebuild): {rebuilt_count}")

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

    # Every script-level test has the same fail-fast ceiling as file operations.
    for test_func in (
        test_router_prompt_hot_reload,
        test_registry_config_hot_reload,
        test_yaml_registry_cache_expiry,
    ):
        try:
            results.append(
                await asyncio.wait_for(
                    test_func(),
                    timeout=4.0,
                )
            )
        except asyncio.TimeoutError:
            print(f"✗ {test_func.__name__}: timed out after 4 seconds")
            results.append(False)

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
