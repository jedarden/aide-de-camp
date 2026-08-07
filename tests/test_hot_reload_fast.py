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
    """Test that router prompt is hot-reloaded."""
    print("\n=== Testing Router Prompt Hot-Reload ===")

    reload_mgr = get_reload_manager()
    original_prompt = reload_mgr.get_prompt('router')

    print(f"Original prompt length: {len(original_prompt)} chars")

    # Touch the router.md file to change mtime
    router_path = Path("prompts/router.md")
    original_content = router_path.read_text()

    # Modify the file
    test_marker = f"\n# Test line added at {time.time()}"
    test_content = original_content + test_marker
    router_path.write_text(test_content)

    # Wait for throttle interval (1 second)
    await asyncio.sleep(1.5)

    # Get the prompt again
    modified_prompt = reload_mgr.get_prompt('router')

    print(f"Modified prompt length: {len(modified_prompt)} chars")

    # Restore original content
    router_path.write_text(original_content)

    # Check if the change was detected
    if test_marker in modified_prompt:
        print("✓ Router prompt hot-reload: PASSED (change detected)")
        return True
    else:
        print("✗ Router prompt hot-reload: FAILED (change not detected)")
        return False


async def test_registry_config_hot_reload():
    """Test that registry config is hot-reloaded."""
    print("\n=== Testing Registry Config Hot-Reload ===")

    import yaml

    reload_mgr = get_reload_manager()
    original_config = reload_mgr.get_config('registry')

    print(f"Original config projects count: {len(original_config.get('projects', {}))}")

    # Touch the registry.yaml file
    registry_path = Path("config/registry.yaml")
    original_content = registry_path.read_text()

    # Parse, modify, and write back
    parsed = yaml.safe_load(original_content)
    parsed['projects']['test-hot-reload-project'] = {
        'description': 'Test project for hot-reload',
        'aliases': ['test', 'hotreload'],
        'cluster': None,
        'namespace': None,
        'intent_support': ['status']
    }
    modified_content = yaml.dump(parsed, default_flow_style=False)
    registry_path.write_text(modified_content)

    # Wait for throttle interval
    await asyncio.sleep(1.5)

    # Get config again
    modified_config = reload_mgr.get_config('registry')

    print(f"Modified config projects count: {len(modified_config.get('projects', {}))}")

    # Restore original content
    registry_path.write_text(original_content)

    # Check if the change was detected
    if 'test-hot-reload-project' in modified_config.get('projects', {}):
        print("✓ Registry config hot-reload: PASSED (change detected)")
        return True
    else:
        print("✗ Registry config hot-reload: FAILED (change not detected)")
        return False


async def test_yaml_registry_force_reload():
    """Test that YAML registry can be force-reloaded."""
    print("\n=== Testing YAML Registry Force Reload ===")

    import yaml
    from registry import get_registry, REGISTRY_PATH

    # Force rebuild to start fresh
    registry1 = get_registry(force=True)
    original_count = len(registry1['projects'])
    print(f"Initial registry project count: {original_count}")

    # Read original content
    original_content = REGISTRY_PATH.read_text()

    # Parse, modify, and write back
    parsed = yaml.safe_load(original_content)
    parsed['projects']['test-force-reload'] = {
        'description': 'Test force reload',
        'aliases': ['forcereload'],
        'cluster': None,
        'namespace': None,
        'intent_support': ['status']
    }
    modified_content = yaml.dump(parsed, default_flow_style=False)
    REGISTRY_PATH.write_text(modified_content)

    # Force reload
    registry2 = get_registry(force=True)
    modified_count = len(registry2['projects'])

    print(f"Registry count after force reload: {modified_count}")

    # Restore original content
    REGISTRY_PATH.write_text(original_content)

    # Clean up by forcing another reload
    get_registry(force=True)

    # Check if the change was detected
    if 'test-force-reload' in registry2.get('projects', {}):
        print("✓ YAML registry force reload: PASSED (change detected)")
        return True
    else:
        print("✗ YAML registry force reload: FAILED (change not detected)")
        return False


async def main():
    print("Fast Hot-Reload Verification Test")
    print("=" * 50)

    results = []

    # Test router prompt hot-reload
    results.append(await test_router_prompt_hot_reload())

    # Test registry config hot-reload
    results.append(await test_registry_config_hot_reload())

    # Test YAML registry force reload
    results.append(await test_yaml_registry_force_reload())

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
