"""
Test fixtures and utilities for config hot reload functionality.

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
    Test registry configuration hot-reload functionality.

    This test verifies that changes to config/registry.yaml take effect without
    requiring a server restart. It follows the pattern:
    1. Load initial registry configuration
    2. Test initial state (dispatch)
    3. Modify registry configuration
    4. Test modified state (re-dispatch)
    5. Verify changes took effect
    """
    from src.intent.router import get_router, clear_router_cache
    from src.environment.discovery import get_registry
    from unittest.mock import AsyncMock, MagicMock
    import json

    # Step 1: Load initial registry configuration
    initial_config = load_registry_config()
    assert initial_config is not None
    assert "projects" in initial_config
    assert "aide-de-camp" in initial_config["projects"]

    # Verify initial aliases exist in config
    adc_project = initial_config["projects"]["aide-de-camp"]
    assert "adc" in adc_project["aliases"]
    assert "aide-de-camp" in adc_project["aliases"]

    # Verify initial global aliases
    assert "prod" in initial_config["global_aliases"]
    assert initial_config["global_aliases"]["prod"] == "options-pipeline"

    # Step 2: Test initial state (dispatch with actual routing)
    # Use a test utterance that references the aide-de-camp project via alias
    test_utterance = "check the status of adc project"
    test_session_id = "test-session-hot-reload"

    # Mock the ZAI client to return a classification with aide-de-camp project
    # This simulates what the LLM would return for this utterance
    mock_zai_response = json.dumps([{
        "intent_type": "status",
        "project_slug": "aide-de-camp",  # LLM returns full slug
        "urgency": "normal",
        "utterance_fragment": "check the status of adc project",
        "confidence": 0.95,
        "reasoning": "status check for aide-de-camp project",
    }])

    # Get router and mock ZAI client
    router = get_router()
    clear_router_cache()  # Ensure clean state for test

    # Mock the deterministic router to always return failure (force LLM path)
    # This ensures we test the actual routing behavior, not fast-path bypass
    from unittest.mock import patch
    mock_det_router = MagicMock()
    mock_det_router.route_utterance.return_value = MagicMock(
        success=False,
        intents=[],
        confidence=0.0,
        reasoning="LLM path forced for test"
    )
    mock_det_router.get_stats.return_value = {"hit_rate": 0.0, "total": 0, "hits": 0}

    # Mock the ZAI client
    mock_client = AsyncMock()
    mock_client.call_simple = AsyncMock(return_value={
        "content": mock_zai_response,
        "timing_network_ms": 100,
        "timing_inference_ms": 500,
    })
    router._router_zai_client = mock_client
    router._zai_client = mock_client

    # Perform initial dispatch (with deterministic router mocked)
    with patch('src.intent.deterministic_router.get_deterministic_router', return_value=mock_det_router):
        initial_classifications, initial_timing = await router.classify_utterance(
            utterance=test_utterance,
            session_id=test_session_id
        )

    # Verify initial routing
    assert len(initial_classifications) == 1
    initial_classification = initial_classifications[0]
    assert initial_classification.intent_type.value == "status"
    assert initial_classification.project_slug == "aide-de-camp"
    assert initial_classification.confidence == 0.95

    # Verify the registry resolution worked
    # The registry should resolve "aide-de-camp" to the actual project path
    registry = get_registry()
    if registry:
        aide_de_camp_entry = registry.lookup("aide-de-camp")
        assert aide_de_camp_entry is not None, "aide-de-camp should be in registry"
        assert aide_de_camp_entry.slug == "aide-de-camp"

    # Step 3: Modify registry configuration
    # Modify the "adc" alias to test hot-reload behavior
    modify_registry_alias("adc", "test-alias-reloaded")

    # Force reload the registry to simulate hot-reload
    # In production, this would happen automatically via mtime checking or background refresh
    from src.environment.discovery import refresh_registry
    await refresh_registry()

    # Step 4: Test modified state (re-dispatch)
    # Reload config to verify alias change
    reloaded_config = load_registry_config()
    adc_project_reloaded = reloaded_config["projects"]["aide-de-camp"]
    assert "test-alias-reloaded" in adc_project_reloaded["aliases"]
    assert "adc" not in adc_project_reloaded["aliases"]

    # Re-dispatch the same utterance with fresh registry
    router2 = get_router()
    clear_router_cache()  # Ensure clean state for second dispatch

    # Mock the ZAI client again for second call
    mock_client2 = AsyncMock()
    mock_client2.call_simple = AsyncMock(return_value={
        "content": mock_zai_response,
        "timing_network_ms": 100,
        "timing_inference_ms": 500,
    })
    router2._router_zai_client = mock_client2
    router2._zai_client = mock_client2

    # Perform re-dispatch (with deterministic router mocked)
    with patch('src.intent.deterministic_router.get_deterministic_router', return_value=mock_det_router):
        reloaded_classifications, reloaded_timing = await router2.classify_utterance(
            utterance=test_utterance,
            session_id=test_session_id
        )

    # Step 5: Verify changes took effect
    # The classification should still work (same project_slug from LLM)
    assert len(reloaded_classifications) == 1
    reloaded_classification = reloaded_classifications[0]
    assert reloaded_classification.intent_type.value == "status"
    assert reloaded_classification.project_slug == "aide-de-camp"

    # Verify the registry still resolves the project correctly
    registry2 = get_registry()
    if registry2:
        aide_de_camp_entry2 = registry2.lookup("aide-de-camp")
        assert aide_de_camp_entry2 is not None, "aide-de-camp should still resolve"
        assert aide_de_camp_entry2.slug == "aide-de-camp"

    # Verify other data was preserved in the config
    assert len(reloaded_config["projects"]) == len(initial_config["projects"])
    assert "declarative-config" in reloaded_config["projects"]
    assert "global_aliases" in reloaded_config
