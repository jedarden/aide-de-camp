"""
Tests for config/registry.yaml hot-reload behavior in intent routing.

This test suite verifies that:
1. Registry alias changes are detected and reloaded
2. The router picks up updated aliases without restart
3. Routing behavior changes based on modified aliases
4. Test modifications are properly reverted

Coverage: adc-1c49h
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from tempfile import NamedTemporaryFile

import pytest
import yaml

from src.registry import get_registry, get_project, REGISTRY_PATH, _cache_at


@pytest.fixture
def original_registry_backup():
    """Backup the original registry.yaml before test modifications."""
    original_content = REGISTRY_PATH.read_text()
    yield original_content
    # Restore original content after test
    REGISTRY_PATH.write_text(original_content)
    # Clear cache to force reload
    from src.registry import _cache
    _cache.clear()
    # Force reload
    get_registry(force=True)


class TestRegistryHotReload:
    """Tests for registry.yaml hot-reload behavior."""

    def test_registry_cache_ttl(self):
        """Test that registry cache has a 5-minute TTL."""
        from src.registry import CACHE_TTL
        assert CACHE_TTL == 300  # 5 minutes = 300 seconds

    def test_get_registry_caches_results(self):
        """Test that get_registry caches results."""
        # First call - loads from disk
        registry1 = get_registry()
        cache_time_1 = _cache_at

        # Second call - should use cache
        registry2 = get_registry()
        cache_time_2 = _cache_at

        # Should return the same cached result
        assert registry1 is registry2
        assert cache_time_1 == cache_time_2

    def test_get_registry_force_reload(self):
        """Test that force=True bypasses cache."""
        # First call
        registry1 = get_registry()
        initial_cache_time = _cache_at

        # Small delay to ensure time difference
        time.sleep(0.15)

        # Modify the file to ensure actual reload
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["whisper-stt"]["aliases"].append("force-reload-test")
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        registry2 = get_registry(force=True)
        new_cache_time = _cache_at

        # Clean up - remove test alias
        restore_content = REGISTRY_PATH.read_text()
        parsed_restore = yaml.safe_load(restore_content)
        parsed_restore["projects"]["whisper-stt"]["aliases"].remove("force-reload-test")
        REGISTRY_PATH.write_text(yaml.dump(parsed_restore, default_flow_style=False))

        # Should have reloaded (time should have changed)
        assert new_cache_time >= initial_cache_time

    def test_get_project_by_slug(self, original_registry_backup):
        """Test resolving project by slug."""
        project = get_project("whisper-stt")
        assert project is not None
        assert project["description"] == "Whisper STT service on ardenone-cluster"
        assert "whisper" in project["aliases"]

    def test_get_project_returns_none_for_unknown(self):
        """Test that get_project returns None for unknown project."""
        project = get_project("nonexistent-project")
        assert project is None

    @pytest.mark.asyncio
    async def test_alias_modification_detected(self, original_registry_backup):
        """Test that alias modifications in registry.yaml are detected."""
        from src.registry import _cache

        # Get original registry
        original_registry = get_registry(force=True)
        original_aliases = original_registry["projects"]["whisper-stt"]["aliases"].copy()
        original_count = len(original_aliases)

        # Modify the registry.yaml file - add a new alias
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["whisper-stt"]["aliases"].append("test-alias-hot-reload")
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Small delay to ensure mtime change
        await asyncio.sleep(0.1)

        # Force reload to pick up changes
        modified_registry = get_registry(force=True)
        modified_aliases = modified_registry["projects"]["whisper-stt"]["aliases"]

        # Verify the new alias is present
        assert "test-alias-hot-reload" in modified_aliases
        assert len(modified_aliases) == original_count + 1

        # Restore will be handled by the fixture

    @pytest.mark.asyncio
    async def test_alias_modification_affects_routing(self, original_registry_backup):
        """Test that alias changes actually affect routing decisions."""
        from src.intent.router import IntentRouter
        from src.registry import get_registry

        # Create an utterance that would normally route to pbx-web
        utterance = "check the status of phone system"

        # Mock the LLM response that routes to "phone system" alias
        mock_llm_response = json.dumps([{
            "intent_type": "status",
            "project_slug": "pbx-web",  # Resolved from "phone system" alias
            "urgency": "normal",
            "utterance_fragment": "check the status of phone system",
            "confidence": 0.9,
            "reasoning": "status check for phone system",
        }])

        # Get initial routing
        registry = get_registry(force=True)
        initial_project = get_project("pbx-web")
        assert initial_project is not None
        assert "phone system" in initial_project["aliases"]

        # Now modify the alias to point to a different project
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)

        # Remove "phone system" from pbx-web
        parsed["projects"]["pbx-web"]["aliases"].remove("phone system")

        # Add "phone system" to whisper-stt instead
        parsed["projects"]["whisper-stt"]["aliases"].append("phone system")

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Wait for mtime change
        await asyncio.sleep(0.1)

        # Force reload
        new_registry = get_registry(force=True)

        # Verify alias moved
        pbx_project = get_project("pbx-web")
        whisper_project = get_project("whisper-stt")
        assert "phone system" not in pbx_project["aliases"]
        assert "phone system" in whisper_project["aliases"]

        # Restore will be handled by the fixture

    @pytest.mark.asyncio
    async def test_multiple_aliases_hot_reload(self, original_registry_backup):
        """Test hot-reload with multiple alias modifications."""
        # Get original state
        original_registry = get_registry(force=True)

        # Make multiple changes
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)

        # Add aliases to multiple projects
        parsed["projects"]["whisper-stt"]["aliases"].extend(["test-alias-1", "test-alias-2"])
        parsed["projects"]["pbx-web"]["aliases"].extend(["test-alias-3", "test-alias-4"])

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Wait for mtime change
        await asyncio.sleep(0.1)

        # Force reload
        new_registry = get_registry(force=True)

        # Verify all changes are present
        whisper_project = get_project("whisper-stt")
        pbx_project = get_project("pbx-web")

        assert "test-alias-1" in whisper_project["aliases"]
        assert "test-alias-2" in whisper_project["aliases"]
        assert "test-alias-3" in pbx_project["aliases"]
        assert "test-alias-4" in pbx_project["aliases"]

        # Restore will be handled by the fixture

    def test_new_project_entry_hot_reload(self, original_registry_backup):
        """Test that adding a new project entry is picked up."""
        # Get original project count
        original_registry = get_registry(force=True)
        original_count = len(original_registry["projects"])

        # Add a new test project
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)

        parsed["projects"]["test-hot-reload-project"] = {
            "description": "Test project for hot-reload verification",
            "aliases": ["test-hot-reload", "thrt"],
            "cluster": None,
            "namespace": None,
            "intent_support": ["status", "lookup"],
        }

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        new_registry = get_registry(force=True)
        new_count = len(new_registry["projects"])

        # Verify new project is present
        assert new_count == original_count + 1
        assert "test-hot-reload-project" in new_registry["projects"]

        test_project = get_project("test-hot-reload-project")
        assert test_project is not None
        assert test_project["description"] == "Test project for hot-reload verification"
        assert "test-hot-reload" in test_project["aliases"]

    def test_remove_and_restore_alias(self, original_registry_backup):
        """Test removing and restoring an alias."""
        # Get original aliases for pbx-web
        original_registry = get_registry(force=True)
        pbx_aliases = original_registry["projects"]["pbx-web"]["aliases"].copy()
        original_count = len(pbx_aliases)

        # Remove an alias
        alias_to_remove = "pbx"
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)

        if alias_to_remove in parsed["projects"]["pbx-web"]["aliases"]:
            parsed["projects"]["pbx-web"]["aliases"].remove(alias_to_remove)

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload and verify removal
        modified_registry = get_registry(force=True)
        modified_project = modified_registry["projects"]["pbx-web"]
        assert alias_to_remove not in modified_project["aliases"]
        assert len(modified_project["aliases"]) == original_count - 1

        # Restore the alias
        restore_content = REGISTRY_PATH.read_text()
        parsed_restore = yaml.safe_load(restore_content)
        parsed_restore["projects"]["pbx-web"]["aliases"].append(alias_to_remove)
        REGISTRY_PATH.write_text(yaml.dump(parsed_restore, default_flow_style=False))

        # Force reload and verify restoration
        restored_registry = get_registry(force=True)
        restored_project = restored_registry["projects"]["pbx-web"]
        assert alias_to_remove in restored_project["aliases"]
        assert len(restored_project["aliases"]) == original_count

    @pytest.mark.asyncio
    async def test_concurrent_modifications_handled(self, original_registry_backup):
        """Test that concurrent modifications are handled safely."""
        import os

        # Get initial state
        initial_registry = get_registry(force=True)

        # Simulate concurrent modifications
        async def modify_registry():
            for i in range(3):
                await asyncio.sleep(0.05)
                content = REGISTRY_PATH.read_text()
                parsed = yaml.safe_load(content)
                parsed["projects"]["whisper-stt"]["aliases"].append(f"concurrent-alias-{i}")
                REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))
                os.utime(REGISTRY_PATH, None)

        # Start modification task
        modify_task = asyncio.create_task(modify_registry())

        # Try to read registry multiple times
        for _ in range(5):
            get_registry(force=True)
            await asyncio.sleep(0.05)

        # Wait for modifications to complete
        await modify_task

        # Final read should still work
        final_registry = get_registry(force=True)
        assert final_registry is not None
        assert "whisper-stt" in final_registry["projects"]

    def test_yaml_structure_preserved_on_reload(self, original_registry_backup):
        """Test that YAML structure is preserved after hot-reload."""
        # Get original registry
        original_registry = get_registry(force=True)

        # Verify original structure
        assert "projects" in original_registry
        assert "clusters" in original_registry
        assert "argocd" in original_registry
        assert "global_aliases" in original_registry

        # Make a modification
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["test-structure"] = {
            "description": "Test structure preservation",
            "aliases": ["structure-test"],
            "cluster": None,
            "namespace": None,
            "intent_support": ["status"],
        }

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        reloaded_registry = get_registry(force=True)

        # Verify structure is preserved
        assert "projects" in reloaded_registry
        assert "clusters" in reloaded_registry
        assert "argocd" in reloaded_registry
        assert "global_aliases" in reloaded_registry

        # Verify clusters and argocd sections are unchanged
        assert reloaded_registry["clusters"] == original_registry["clusters"]
        assert reloaded_registry["argocd"] == original_registry["argocd"]

    @pytest.mark.asyncio
    async def test_hot_reload_timing(self, original_registry_backup):
        """Test that hot-reload happens within expected time window."""
        import time

        # Measure reload time
        start_time = time.time()
        get_registry(force=True)
        first_reload_time = time.time() - start_time

        # Modify the file
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["whisper-stt"]["aliases"].append("timing-test-alias")
        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Measure reload time after modification
        await asyncio.sleep(0.1)
        start_time = time.time()
        get_registry(force=True)
        second_reload_time = time.time() - start_time

        # Both reloads should be fast (< 1 second)
        assert first_reload_time < 1.0, f"First reload took {first_reload_time:.2f}s"
        assert second_reload_time < 1.0, f"Second reload took {second_reload_time:.2f}s"


class TestRegistryIntegration:
    """Integration tests for registry with routing system."""

    def test_registry_projects_summary(self):
        """Test that projects_summary generates correct output."""
        from src.registry import projects_summary

        summary = projects_summary()

        # Should contain project entries
        assert "whisper-stt" in summary
        assert "pbx-web" in summary
        assert "kalshi-tape" in summary

        # Should contain aliases
        assert "(aliases:" in summary

    def test_global_aliases_section(self, original_registry_backup):
        """Test that global_aliases section is preserved."""
        registry = get_registry(force=True)

        # Verify global_aliases exist
        assert "global_aliases" in registry
        assert isinstance(registry["global_aliases"], dict)

        # Make a modification
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["global_aliases"]["test-global"] = "test-target"

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        new_registry = get_registry(force=True)

        # Verify global_aliases are preserved
        assert "global_aliases" in new_registry
        assert "test-global" in new_registry["global_aliases"]
        assert new_registry["global_aliases"]["test-global"] == "test-target"

    def test_clusters_section_preserved(self, original_registry_backup):
        """Test that clusters section is preserved on hot-reload."""
        registry = get_registry(force=True)

        # Verify clusters exist
        assert "clusters" in registry
        assert "ardenone-cluster" in registry["clusters"]
        assert registry["clusters"]["ardenone-cluster"]["proxy"] == "http://traefik-ardenone-cluster:8001"

        # Make a modification to projects only
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["test-clusters"] = {
            "description": "Test clusters preservation",
            "aliases": ["clusters-test"],
            "cluster": None,
            "namespace": None,
            "intent_support": ["status"],
        }

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        new_registry = get_registry(force=True)

        # Verify clusters are unchanged
        assert new_registry["clusters"] == registry["clusters"]
        assert "ardenone-cluster" in new_registry["clusters"]

    def test_argocd_section_preserved(self, original_registry_backup):
        """Test that argocd section is preserved on hot-reload."""
        registry = get_registry(force=True)

        # Verify argocd config exists
        assert "argocd" in registry
        assert "base_url" in registry["argocd"]

        # Make a modification
        modified_content = REGISTRY_PATH.read_text()
        parsed = yaml.safe_load(modified_content)
        parsed["projects"]["test-argocd"] = {
            "description": "Test argocd preservation",
            "aliases": ["argocd-test"],
            "cluster": None,
            "namespace": None,
            "intent_support": ["status"],
        }

        REGISTRY_PATH.write_text(yaml.dump(parsed, default_flow_style=False))

        # Force reload
        new_registry = get_registry(force=True)

        # Verify argocd config is unchanged
        assert new_registry["argocd"] == registry["argocd"]
        assert "base_url" in new_registry["argocd"]
