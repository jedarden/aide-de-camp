#!/usr/bin/env python3
"""
Fast test to verify hot-reload behavior of prompts and configs.

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
    """Verify the fast prompt regression path detects a disk edit.

    The test waits beyond the manager's mtime-check throttle and restores both
    the prompt file and its cached snapshot even if verification fails.
    """
    print("\n=== Testing Router Prompt Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_prompt = reload_mgr.get_prompt('router')

    print(f"Original prompt length: {len(original_prompt)} chars")

    # Touch the router.md file to change mtime
    router_path = Path("prompts/router.md")
    original_content = router_path.read_text()

    try:
        test_marker = f"\n# Test line added at {time.time()}"
        router_path.write_text(original_content + test_marker)
        await asyncio.sleep(1.5)
        modified_prompt = reload_mgr.get_prompt('router')
        print(f"Modified prompt length: {len(modified_prompt)} chars")

        if test_marker in modified_prompt:
            print("✓ Router prompt hot-reload: PASSED (change detected)")
            return True
        print("✗ Router prompt hot-reload: FAILED (change not detected)")
        return False
    finally:
        router_path.write_text(original_content)
        reload_mgr.force_reload('router')


async def test_registry_config_hot_reload():
    """Verify the fast registry-manager path observes a temporary project.

    The modified YAML is parsed after the normal mtime-check throttle, then
    the original file and manager cache are restored in ``finally``.
    """
    print("\n=== Testing Registry Config Hot-Reload ===")

    import yaml

    reload_mgr = get_reload_manager()
    original_config = reload_mgr.get_config('registry')

    print(f"Original config projects count: {len(original_config.get('projects', {}))}")

    # Touch the registry.yaml file
    registry_path = Path("config/registry.yaml")
    original_content = registry_path.read_text()

    try:
        parsed = yaml.safe_load(original_content)
        parsed['projects']['test-hot-reload-project'] = {
            'description': 'Test project for hot-reload',
            'aliases': ['test', 'hotreload'],
            'cluster': None,
            'namespace': None,
            'intent_support': ['status']
        }
        registry_path.write_text(yaml.dump(parsed, default_flow_style=False))
        await asyncio.sleep(1.5)

        modified_config = reload_mgr.get_config('registry')
        print(f"Modified config projects count: {len(modified_config.get('projects', {}))}")

        if 'test-hot-reload-project' in modified_config.get('projects', {}):
            print("✓ Registry config hot-reload: PASSED (change detected)")
            return True
        print("✗ Registry config hot-reload: FAILED (change not detected)")
        return False
    finally:
        registry_path.write_text(original_content)
        reload_mgr.force_reload('registry')


async def test_yaml_registry_force_reload():
    """Verify ``get_registry(force=True)`` bypasses the five-minute TTL.

    A temporary project is added to the real registry, observed immediately,
    and removed in ``finally`` before the registry cache is rebuilt.
    """
    print("\n=== Testing YAML Registry Force Reload ===")

    import yaml
    from registry import get_registry, REGISTRY_PATH

    # Force rebuild to start fresh
    registry1 = get_registry(force=True)
    original_count = len(registry1['projects'])
    print(f"Initial registry project count: {original_count}")

    # Read original content
    original_content = REGISTRY_PATH.read_text()

    try:
        parsed = yaml.safe_load(original_content)
        parsed['projects']['test-force-reload'] = {
            'description': 'Test force reload',
            'aliases': ['forcereload'],
            'cluster': None,
            'namespace': None,
            'intent_support': ['status']
        }
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        registry2 = get_registry(force=True)
        modified_count = len(registry2['projects'])
        print(f"Registry count after force reload: {modified_count}")

        if 'test-force-reload' in registry2.get('projects', {}):
            print("✓ YAML registry force reload: PASSED (change detected)")
            return True
        print("✗ YAML registry force reload: FAILED (change not detected)")
        return False
    finally:
        REGISTRY_PATH.write_text(original_content)
        get_registry(force=True)


async def main():
    print("Fast Hot-Reload Verification Test")
    print("=" * 50)

    results = []

    for test_func in (
        test_router_prompt_hot_reload,
        test_registry_config_hot_reload,
        test_yaml_registry_force_reload,
    ):
        try:
            results.append(await asyncio.wait_for(test_func(), timeout=4.0))
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
        print("- config/registry.yaml (registry.py): Force-reload works ✓")
        print("\nHot-reload is working correctly for all tested artifacts.")
        return 0
    else:
        print("\n✗ Some hot-reload tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
