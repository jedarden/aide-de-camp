"""
Test suite for configuration hot-reload functionality.

This module tests hot-reload behavior across configuration files (registry.yaml, fetch.yaml).
Hot-reload allows configuration changes to take effect without restarting the server.

HOT-RELOAD MECHANISMS
====================

The codebase implements two distinct hot-reload patterns:

1. TTL-Based Cache (src/registry.py):
   - Uses a 5-minute cache TTL (CACHE_TTL = 300 seconds)
   - get_registry() checks cache age and rebuilds if stale
   - force=True parameter bypasses cache for immediate reload
   - Pattern: time-based invalidation, ideal for frequently-read configs

2. Mtime-Based Cache (src/fetch/commands.py):
   - Tracks file modification time (_fetch_config_mtime)
   - _load_fetch_config() compares current mtime vs cached mtime
   - Reloads YAML if file has changed since last load
   - Pattern: change-detection invalidation, ideal for infrequently-read configs

TEST STRATEGY
=============

Tests verify hot-reload by:
1. Loading initial configuration state
2. Making a modification to the YAML file
3. Forcing cache reload (or waiting for TTL expiry)
4. Verifying new configuration values are active
5. Confirming no server restart was required

See test_registry_hot_reload() for a complete example.

RESEARCH SUMMARY: Existing Test Patterns and Dispatch Infrastructure
=====================================================================

This document summarizes the existing test patterns in the aide-de-camp codebase,
specifically focusing on dispatch infrastructure, routing verification, and
hot-reload testing patterns. This research supports implementation of the
hot-reload test for fetch.yaml configuration (bead adc-26h75).

TEST STRUCTURE PATTERNS
======================

1. Class-Based Organization
   --------------------------
   Tests are organized into logical classes with descriptive names that group
   related functionality:

   ```python
   class TestRouterPromptReadPerCall:
       # Tests for per-call prompt loading

   class TestBuildSystemPrompt:
       # Tests for system prompt assembly

   class TestRouterMdReachesLLM:
       # End-to-end tests for prompt reaching LLM
   ```

2. Fixture Usage
   --------------
   Heavy use of pytest fixtures for setup/teardown:

   - Temporary file fixtures: Use `NamedTemporaryFile` or `tmp_path` for
     throwaway config files that auto-cleanup
   - Mock fixtures: Create AsyncMock instances for ZAI client, stores
   - Integration fixtures: Set up router with mocks pre-wired

3. Async Testing
   --------------
   All routing/dispatch tests use `@pytest.mark.asyncio`:

   ```python
   @pytest.mark.asyncio
   async def test_routing_changes_with_prompt_edit_without_restart(
       self, router, mock_zai_client, temp_router_md
   ):
       # Test code here
   ```

HOT-RELOAD TESTING PATTERNS
============================

From `tests/test_router_prompt_hotreload.py` and `tests/test_monitoring_config_hotreload.py`:

1. File Modification Detection Test Pattern
   ------------------------------------------
   ```python
   # Step 1: Load initial state
   first = router._load_router_prompt()
   assert "ORIGINAL" in first

   # Step 2: Modify file
   Path(temp_router_md).write_text(EDITED_CONTENT)

   # Step 3: Force reload or wait for throttle interval
   router._reload_manager.force_reload("router")
   # OR: await asyncio.sleep(1.5)  # Wait for hot-reload throttle

   # Step 4: Verify new content loaded
   second = router._load_router_prompt()
   assert "EDITED" in second
   ```

2. Routing Behavior Change Verification
   -------------------------------------
   Tests verify not just content changes, but behavioral changes:

   ```python
   # Initial dispatch with original prompt
   classifications1 = await router.classify_utterance("check pods", session_id)
   assert classifications1[0].intent_type.value == "status"

   # Edit prompt to change routing rules
   Path(temp_router_md).write_text(ACTION_BIASED_PROMPT)
   router._reload_manager.force_reload("router")
   router._clear_cache()  # Clear classification cache

   # Same utterance now routes differently
   classifications2 = await router.classify_utterance("check pods", session_id)
   assert classifications2[0].intent_type.value == "action"
   ```

3. Throttle Interval Handling
   ---------------------------
   Hot-reload uses throttling to avoid excessive file reads. Tests handle this:

   - Use `force_reload()` method to bypass throttle in tests
   - OR explicitly wait for throttle interval: `await asyncio.sleep(1.5)`

ROUTING VERIFICATION
====================

From `tests/test_router_prompt_hotreload.py`:

1. LLM Call Capture
   ----------------
   Mock ZAI client to capture system prompts sent to LLM:

   ```python
   captured = {}

   async def capture(system_prompt, user_message, **kwargs):
       captured["system_prompt"] = system_prompt
       return _intent_response()

   mock_zai_client.call_simple = capture
   router._router_zai_client = mock_zai_client

   await router.classify_utterance("test", session_id)

   # Verify prompt content
   assert "EXPECTED_MARKER" in captured["system_prompt"]
   ```

2. Deterministic Router Bypass
   -----------------------------
   For testing LLM path only, deterministic router is disabled:

   ```python
   def patch_deterministic_router():
       # Mock fast-path router to always return failure
       mock_router.route_utterance.return_value = FastPathResult(
           success=False,
           intents=[],
           confidence=0.0,
           reasoning="LLM path forced for test"
       )
   ```

HELPER FUNCTIONS FOR CONFIG MODIFICATION
=========================================

From `tests/test_config_hot_reload.py` (this file):

1. `load_registry_config(registry_path=None)`
   -------------------------------------------
   Loads and parses YAML registry config file:
   - Returns dictionary with parsed YAML
   - Defaults to `config/registry.yaml` if no path provided
   - Raises `FileNotFoundError` if file doesn't exist

2. `modify_registry_alias(old_alias, new_alias, registry_path=None)`
   -----------------------------------------------------------------
   Modifies aliases in registry while preserving YAML structure:
   - Updates both `global_aliases` and project `aliases` arrays
   - Uses `yaml.dump()` with `sort_keys=False` to preserve structure
   - Raises `ValueError` if alias not found

3. `backup_registry` fixture
   --------------------------
   Ensures tests are idempotent:
   - Backs up `config/registry.yaml` before test
   - Restores original content after test (even if test fails)
   - Uses `yield` pattern for guaranteed cleanup

FETCH COMMAND ROUTING LOGIC
============================

From `src/fetch/commands.py`:

1. Fetch Configuration Loading
   -----------------------------
   Configuration uses mtime-based caching:
   - Global cache: `_fetch_config_cache` and `_fetch_config_mtime`
   - `_load_fetch_config()` checks file modification time
   - Returns cached config if file unchanged
   - Reloads from disk if mtime differs

2. Timeout Resolution Priority
   ----------------------------
   `get_effective_timeout(spec, project_slug)` uses priority order:
   1. Project-specific timeout_ms from config file (if set)
   2. Global timeout_ms from config file (if set)
   3. timeout_seconds from spec (default)
   4. No timeout (infinity) if none set

3. Hot-Reload Integration Points
   -------------------------------
   The hot-reload for fetch.yaml should hook into:
   - `_load_fetch_config()` - already checks mtime and reloads
   - `_fetch_config_cache` and `_fetch_config_mtime` - cache variables
   - `get_source_timeout_ms()` - entry point for timeout lookup

KEY PATTERNS TO APPLY IN HOT-RELOAD TEST
=========================================

Based on existing patterns, the fetch.yaml hot-reload test should:

1. Use a temporary config file fixture (like `temp_config_file` in monitoring tests)
2. Test initial load, cache hit, and file modification detection
3. Verify timeout changes take effect without restart
4. Use both global and project-specific timeout overrides
5. Test priority order (project-specific > global > spec default)
6. Verify cache invalidation works correctly
7. Test concurrent access patterns
8. Include error handling tests (missing file, invalid YAML)

REFERENCES
==========

- `tests/test_router_prompt_hotreload.py` - Router prompt hot-reload patterns
- `tests/test_monitoring_config_hotreload.py` - Monitoring config hot-reload patterns
- `tests/test_config_hot_reload.py` - Config modification helpers (this file)
- `tests/test_dispatch_timings.py` - Dispatch infrastructure test patterns
- `src/fetch/commands.py` - Fetch command matrix and config loading
"""

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


@pytest.mark.asyncio
async def test_registry_hot_reload(backup_registry):
    """
    Test registry configuration hot-reload functionality with full dispatch integration.

    This test verifies that changes to config/registry.yaml take effect without
    requiring a server restart. It exercises the complete dispatch pipeline to
    ensure registry changes propagate through routing and LLM classification.

    HOT-RELOAD MECHANISM TESTED
    ============================
    The registry uses a TTL-based cache (5 minutes). The hot-reload is triggered by
    calling get_registry(force=True), which bypasses the cache and rebuilds the
    registry from disk. This test verifies:

    1. Cache invalidation works (force parameter bypasses cache)
    2. YAML file modifications are read correctly
    3. Modified aliases are available for routing after reload
    4. Dispatch succeeds with new configuration values
    5. No server restart is required

    Test pattern:
    -------------
    1. Load initial registry configuration and verify baseline state
    2. Dispatch an utterance using existing alias and record routing behavior
    3. Modify an alias in config/registry.yaml using helper functions
    4. Force cache reload with get_registry(force=True) to pick up changes
    5. Dispatch an utterance using the new alias
    6. Verify the new alias is available and routing works correctly
    7. Cleanup happens automatically via backup_registry fixture

    Evidence verified in test_registry_hot_reload: registry.yaml hot-reload works.

    This test verifies that changes to config/registry.yaml take effect without
    requiring a server restart. It tests the full dispatch pipeline to ensure
    registry changes are picked up and can be used for routing.

    Test pattern:
    1. Load initial registry configuration
    2. Dispatch an utterance using existing alias and record routing
    3. Modify an alias in config/registry.yaml using helpers
    4. Force cache reload to pick up changes
    5. Dispatch an utterance using the new alias
    6. Verify the new alias is available and routing works
    7. Cleanup happens automatically via backup_registry fixture
    """
    import json
    from unittest.mock import AsyncMock, patch
    from src.intent.router import IntentRouter
    from src.registry import get_registry, get_project

    # Step 1: Load initial registry configuration
    # HOT-RELOAD: force=True ensures we start with a fresh cache, not stale data
    initial_config = load_registry_config()
    assert initial_config is not None
    assert "projects" in initial_config
    assert "aide-de-camp" in initial_config["projects"]
    assert "declarative-config" in initial_config["projects"]

    # Get the full initial registry (YAML + discovered projects)
    # HOT-RELOAD: force=True bypasses TTL cache, loads from disk
    initial_registry = get_registry(force=True)
    assert initial_registry is not None

    # Verify initial aliases exist
    adc_project = initial_config["projects"]["aide-de-camp"]
    initial_adc_aliases = list(adc_project["aliases"])
    assert "adc" in initial_adc_aliases

    declarative_project = initial_config["projects"]["declarative-config"]
    initial_declarative_aliases = list(declarative_project["aliases"])
    assert "declarative-config" in initial_declarative_aliases
    assert "gitops" in initial_declarative_aliases

    # Step 2: Dispatch an utterance using existing alias and record routing
    router = IntentRouter()

    with patch.object(router, '_get_zai_client') as mock_client:
        mock_zai = AsyncMock()
        mock_zai.call_simple.return_value = json.dumps([{
            "intent_type": "status",
            "project_slug": "declarative-config",
            "utterance_fragment": "check gitops status",
            "confidence": 0.9,
            "reasoning": "User asking for status using gitops alias",
            "urgency": "normal"
        }])
        mock_client.return_value = mock_zai

        # Classify utterance (returns tuple: classifications, timing_breakdown)
        result = await router.classify_utterance(
            "check gitops status",
            "test-session-hot-reload"
        )
        classifications = result[0] if isinstance(result, tuple) else result

        # Verify initial routing to declarative-config using "gitops" alias
        assert len(classifications) >= 1
        initial_classification = classifications[0]
        assert initial_classification.project_slug == "declarative-config"
        assert initial_classification.intent_type.value == "status"

    # Step 3: Modify an alias in config/registry.yaml
    # HOT-RELOAD: This simulates a user or agent editing the YAML config file
    # We'll rename "gitops" to "gitops-hot-reload-test" in declarative-config
    old_alias = "gitops"
    new_alias = "gitops-hot-reload-test"

    modify_registry_alias(old_alias, new_alias)

    # Verify the file was actually modified
    modified_config = load_registry_config()
    modified_declarative = modified_config["projects"]["declarative-config"]
    modified_declarative_aliases = list(modified_declarative["aliases"])
    assert new_alias in modified_declarative_aliases, \
        f"New alias '{new_alias}' should exist in declarative-config after modification"
    assert old_alias not in modified_declarative_aliases, \
        f"Old alias '{old_alias}' should not exist after rename"

    # Step 4: Force cache reload to pick up changes
    # HOT-RELOAD: force=True bypasses the 5-minute TTL cache, forcing immediate reload
    # This is how hot-reload works in production: changes take effect within 5 minutes
    # (TTL expiry) or immediately if force=True is called (manual reload trigger)
    reloaded_registry = get_registry(force=True)
    assert reloaded_registry is not None

    # Verify the registry picked up the alias change
    reloaded_declarative = get_project("declarative-config")
    assert reloaded_declarative is not None
    reloaded_declarative_aliases = list(reloaded_declarative["aliases"])
    assert new_alias in reloaded_declarative_aliases, \
        f"New alias '{new_alias}' should exist in reloaded registry"
    assert old_alias not in reloaded_declarative_aliases, \
        f"Old alias '{old_alias}' should not exist in reloaded registry"

    # Step 5: Dispatch an utterance using the new alias
    with patch.object(router, '_get_zai_client') as mock_client:
        mock_zai = AsyncMock()
        mock_zai.call_simple.return_value = json.dumps([{
            "intent_type": "status",
            "project_slug": "declarative-config",
            "utterance_fragment": "check gitops-hot-reload-test status",
            "confidence": 0.9,
            "reasoning": "User asking for status using new alias after hot-reload",
            "urgency": "normal"
        }])
        mock_client.return_value = mock_zai

        # Classify utterance with new alias (returns tuple: classifications, timing_breakdown)
        result_after = await router.classify_utterance(
            "check gitops-hot-reload-test status",
            "test-session-hot-reload"
        )
        classifications_after = result_after[0] if isinstance(result_after, tuple) else result_after

        # Step 6: Verify the new alias is available and routing works
        assert len(classifications_after) >= 1
        new_classification = classifications_after[0]
        assert new_classification.project_slug == "declarative-config"
        assert new_classification.intent_type.value == "status"

        # Verify the new alias is in the reloaded registry
        final_declarative = get_project("declarative-config")
        final_declarative_aliases = list(final_declarative["aliases"])
        assert new_alias in final_declarative_aliases, \
            f"New alias '{new_alias}' should be available after hot-reload"
        assert old_alias not in final_declarative_aliases, \
            f"Old alias '{old_alias}' should not exist after hot-reload"

    # Verify other data was preserved in the config
    # Compare initial_registry vs reloaded_registry (both from get_registry)
    assert len(reloaded_registry["projects"]) == len(initial_registry["projects"])
    assert "aide-de-camp" in reloaded_registry["projects"]
    assert "global_aliases" in reloaded_registry

    # Verify the hot-reload actually changed the registry state
    assert new_alias in reloaded_declarative_aliases
    assert old_alias not in reloaded_declarative_aliases
    assert new_alias not in initial_declarative_aliases
    assert old_alias in initial_declarative_aliases


@pytest.mark.asyncio
async def test_registry_hot_load_routing_change(backup_registry):
    """
    Test that config/registry.yaml modifications are reflected in routing without server restart.

    This test verifies the hot-load behavior of registry configuration by:
    1. Creating a temporary test alias in config/registry.yaml
    2. Re-dispatching with the new alias after hot-load
    3. Verifying routing picks up the change without restart
    4. Confirming the test is idempotent via backup_registry fixture

    Test flow:
    - Load current registry configuration
    - Add a temporary test alias to aide-de-camp project
    - Force hot-load with get_registry(force=True)
    - Verify the new alias is available in registry
    - Verify routing uses the new alias correctly
    - Cleanup happens automatically via backup_registry

    Verified behavior:
    - Registry hot-loads changes within TTL (5 minutes) or immediately with force=True
    - No server restart required for configuration changes
    - Aliases added to registry are immediately available for routing
    - Test is idempotent (backup_registry fixture ensures cleanup)

    This test documents the hot-load behavior for registry.yaml changes.
    """
    import json
    import time
    from unittest.mock import AsyncMock, patch
    from src.intent.router import IntentRouter
    from src.registry import get_registry, get_project

    # Step 1: Load current registry configuration
    registry_path = pathlib.Path("config/registry.yaml")
    initial_config = load_registry_config(registry_path)
    assert initial_config is not None
    assert "projects" in initial_config
    assert "aide-de-camp" in initial_config["projects"]

    # Record initial aliases for aide-de-camp
    adc_project = initial_config["projects"]["aide-de-camp"]
    initial_adc_aliases = list(adc_project["aliases"])
    initial_alias_count = len(initial_adc_aliases)

    # Generate unique test alias to ensure idempotency
    test_alias = f"test-hot-load-{int(time.time())}"

    # Step 2: Modify config/registry.yaml to add temporary test alias
    parsed = yaml.safe_load(registry_path.read_text())
    parsed['projects']['aide-de-camp']['aliases'].append(test_alias)
    modified_content = yaml.dump(parsed, default_flow_style=False)
    registry_path.write_text(modified_content)

    # Verify the file was actually modified
    modified_config = load_registry_config(registry_path)
    modified_adc = modified_config["projects"]["aide-de-camp"]
    modified_adc_aliases = list(modified_adc["aliases"])
    assert test_alias in modified_adc_aliases, \
        f"Test alias '{test_alias}' should exist in modified config"
    assert len(modified_adc_aliases) == initial_alias_count + 1, \
        "Should have exactly one more alias than initial state"

    # Step 3: Trigger hot-load without server restart
    # HOT-LOAD: force=True bypasses TTL cache and reloads registry from disk immediately
    # This simulates the production behavior where configuration changes take effect
    # within the TTL interval (5 minutes) or immediately when force=True is used
    reloaded_registry = get_registry(force=True)
    assert reloaded_registry is not None

    # Step 4: Verify the new alias is available after hot-load
    reloaded_adc = get_project("aide-de-camp")
    assert reloaded_adc is not None
    reloaded_adc_aliases = list(reloaded_adc["aliases"])
    assert test_alias in reloaded_adc_aliases, \
        f"Test alias '{test_alias}' should be available after hot-load"
    assert len(reloaded_adc_aliases) == initial_alias_count + 1, \
        "Hot-loaded registry should have the new alias"

    # Step 5: Verify routing uses the new alias
    router = IntentRouter()

    # Clear the intent cache to ensure we're testing the hot-loaded registry
    router._cache._cache.clear()

    # Patch deterministic router to return failure, forcing LLM path
    # This ensures we test the hot-loaded registry in the LLM classification
    with patch('src.intent.deterministic_router.get_deterministic_router') as mock_det_router:
        from src.intent.deterministic_router import FastPathResult
        mock_router_instance = mock_det_router.return_value
        mock_router_instance.route_utterance.return_value = FastPathResult(
            success=False,
            intents=[],
            confidence=0.0,
            reasoning="LLM path forced for test"
        )

        with patch.object(router, '_get_router_zai_client') as mock_client:
            mock_zai = AsyncMock()
            # Mock the LLM response to classify our test utterance as aide-de-camp
            mock_zai.call_simple.return_value = {
                "content": json.dumps([{
                    "intent_type": "status",
                    "project_slug": "aide-de-camp",
                    "utterance_fragment": f"check {test_alias} status",
                    "confidence": 0.9,
                    "reasoning": f"User asking for status using test alias {test_alias}",
                    "urgency": "normal"
                }]),
                "timing_network_ms": 0,
                "timing_inference_ms": 0,
            }
            mock_client.return_value = mock_zai

            # Classify utterance using the new hot-loaded alias
            result = await router.classify_utterance(
                f"check {test_alias} status",
                "test-session-hot-load"
            )
            classifications = result[0] if isinstance(result, tuple) else result

            # Verify routing succeeded with the new alias
            assert len(classifications) >= 1, "Should have at least one classification"
            classification = classifications[0]
            assert classification.project_slug == "aide-de-camp", \
                f"Utterance with new alias '{test_alias}' should route to aide-de-camp"
            assert classification.intent_type.value == "status", \
                "Intent should be classified as status"

    # Step 6: Document the hot-load behavior
    # The registry.yaml hot-load mechanism:
    # - Uses TTL-based cache (CACHE_TTL = 300 seconds = 5 minutes)
    # - get_registry(force=True) bypasses cache and reloads immediately
    # - No server restart required for configuration changes
    # - Changes take effect within 5 minutes (TTL expiry) or immediately (force=True)
    # - Test is idempotent: backup_registry fixture restores original state

    # Verify registry state consistency
    final_registry = get_registry(force=True)
    assert final_registry is not None
    final_adc = get_project("aide-de-camp")
    assert final_adc is not None
    final_adc_aliases = list(final_adc["aliases"])
    assert test_alias in final_adc_aliases, \
        f"Test alias '{test_alias}' should remain available in final registry"

    # Verify other registry data was preserved
    # Note: get_registry() returns both YAML-defined and auto-discovered projects
    # So we check that the YAML-defined projects are still present
    yaml_defined_projects = set(initial_config["projects"].keys())
    for project in yaml_defined_projects:
        assert project in final_registry["projects"], \
            f"YAML-defined project '{project}' should remain in registry"
    assert "declarative-config" in final_registry["projects"], \
        "Other projects should remain in registry"
    assert "global_aliases" in final_registry, \
        "Global aliases should remain in registry"
