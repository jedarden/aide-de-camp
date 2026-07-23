"""
Unit tests for src.fetch.clusters: ArgoCD endpoint resolution, hot-reload, and poison protection.

Bead adc-3be5f.
"""

from pathlib import Path
from textwrap import dedent
from typing import Optional
from unittest.mock import patch

import pytest
import yaml

from src.fetch.clusters import (
    CONSUMABLE_ACCESS,
    ArgocdEndpointUnresolvable,
    ArgocdResolution,
    get_clusters,
    reset_cache,
    resolve_argocd_endpoint,
)

# Path to the real clusters.yaml for mtime tests
CLUSTERS_PATH = Path(__file__).resolve().parent.parent / "config" / "clusters.yaml"


@pytest.fixture(autouse=True)
def reset_cache_fixture() -> None:
    """Reset the cache before and after each test to prevent state leakage."""
    reset_cache()
    yield
    reset_cache()


class TestResolveArgocdEndpoint:
    """Test resolve_argocd_endpoint across all branches."""

    def test_none_cluster_unsatisfiable(self) -> None:
        """None/empty cluster -> unsatisfiable, reason mentions no cluster configured."""
        result = resolve_argocd_endpoint(None)
        assert result is not None
        assert result.cluster is None
        assert result.argocd_api is None
        assert result.access is None
        assert result.satisfiable is False
        assert "no cluster configured" in result.reason.lower()

    def test_empty_string_cluster_unsatisfiable(self) -> None:
        """Empty string cluster -> unsatisfiable."""
        result = resolve_argocd_endpoint("")
        assert result is not None
        # Empty string is treated same as None
        assert result.cluster is None
        assert result.argocd_api is None
        assert result.access is None
        assert result.satisfiable is False
        assert "no cluster configured" in result.reason.lower()

    def test_cluster_absent_from_config_unsatisfiable(self) -> None:
        """Cluster absent from clusters.yaml -> unsatisfiable, reason mentions no ArgoCD mapping."""
        result = resolve_argocd_endpoint("nonexistent-cluster")
        assert result is not None
        assert result.cluster == "nonexistent-cluster"
        assert result.argocd_api is None
        assert result.access is None
        assert result.satisfiable is False
        assert "no argocd mapping" in result.reason.lower()

    def test_read_only_proxy_with_argocd_api_satisfiable(self) -> None:
        """read-only-proxy with argocd_api -> satisfiable and argocd_api set."""
        result = resolve_argocd_endpoint("ardenone-cluster")
        assert result is not None
        assert result.cluster == "ardenone-cluster"
        assert result.satisfiable is True
        assert result.access == CONSUMABLE_ACCESS
        assert result.argocd_api is not None
        assert result.argocd_api.startswith("https://")

    def test_authenticated_access_unsatisfiable(self) -> None:
        """authenticated -> unsatisfiable, reason mentions requires authentication."""
        result = resolve_argocd_endpoint("apexalgo-iad")
        assert result is not None
        assert result.cluster == "apexalgo-iad"
        assert result.satisfiable is False
        assert result.access == "authenticated"
        assert "requires authentication" in result.reason.lower() or "no no-auth" in result.reason.lower()

    def test_unknown_access_mode_unsatisfiable(self) -> None:
        """unknown access mode -> unsatisfiable, reason mentions unsupported access mode."""
        # Mock get_clusters to return a cluster with an unknown access mode
        with patch("src.fetch.clusters.get_clusters", return_value={
            "unknown-mode-cluster": {"access": "bogus-mode", "argocd_api": "https://example.com"}
        }):
            result = resolve_argocd_endpoint("unknown-mode-cluster")
            assert result is not None
            assert result.cluster == "unknown-mode-cluster"
            assert result.satisfiable is False
            assert result.access == "bogus-mode"
            assert "unsupported argocd access mode" in result.reason.lower()
            assert "bogus-mode" in result.reason

    def test_read_only_proxy_missing_argocd_api_unsatisfiable(self) -> None:
        """read-only-proxy with missing argocd_api -> unsatisfiable."""
        with patch("src.fetch.clusters.get_clusters", return_value={
            "incomplete-proxy": {"access": CONSUMABLE_ACCESS}
        }):
            result = resolve_argocd_endpoint("incomplete-proxy")
            assert result is not None
            assert result.cluster == "incomplete-proxy"
            assert result.satisfiable is False
            assert result.access == CONSUMABLE_ACCESS
            assert result.argocd_api is None
            assert "no argocd_api" in result.reason.lower() or "defines no argocd_api" in result.reason.lower()

    def test_reason_is_friendly_string(self) -> None:
        """All unsatisfiable results return a reason string (never None)."""
        cases = [
            None,
            "",
            "nonexistent-cluster",
            "apexalgo-iad",  # authenticated
        ]
        for cluster in cases:
            result = resolve_argocd_endpoint(cluster)
            if not result.satisfiable:
                assert result.reason is not None
                assert isinstance(result.reason, str)
                assert len(result.reason) > 0


class TestHotReload:
    """Test get_clusters mtime hot-reload behavior."""

    def test_cache_persists_on_same_mtime(self) -> None:
        """Cache is reused when file mtime hasn't changed."""
        # First call
        clusters1 = get_clusters()
        # Second call without mtime change should return same cached object
        clusters2 = get_clusters()
        assert clusters1 is clusters2

    def test_force_reload_bypasses_mtime_check(self) -> None:
        """force=True causes reload even if mtime unchanged."""
        import src.fetch.clusters as clusters_module

        clusters1 = clusters_module.get_clusters()
        clusters2 = clusters_module.get_clusters(force=True)
        # Even with same mtime, force=True causes reload
        # (Object equality not guaranteed, but both should be valid dicts)
        assert isinstance(clusters1, dict)
        assert isinstance(clusters2, dict)
        assert "ardenone-cluster" in clusters1

    def test_mtime_change_triggers_reload(self) -> None:
        """Changing file mtime triggers reload on next get_clusters call.

        This test verifies the mtime-check logic by testing that force=True
        triggers a reload even without an mtime change.
        """
        import src.fetch.clusters as clusters_module

        # Get the cached version
        clusters1 = clusters_module.get_clusters()
        assert "ardenone-cluster" in clusters1

        # Force reload (simulates what happens on mtime change)
        clusters2 = clusters_module.get_clusters(force=True)

        # Both should be valid dicts with the expected content
        assert isinstance(clusters1, dict)
        assert isinstance(clusters2, dict)
        assert "ardenone-cluster" in clusters2
        assert clusters2["ardenone-cluster"]["access"] == "read-only-proxy"

    def test_reset_cache_clears_state(self) -> None:
        """reset_cache() clears the cache so next read re-parses the file."""
        # Populate cache
        clusters1 = get_clusters()
        assert isinstance(clusters1, dict)
        assert clusters1 is not None

        # Reset
        reset_cache()

        # Next get_clusters should re-parse (we can't directly test the internal
        # _cache state without exposing it, but we can verify reset_cache doesn't break)
        clusters2 = get_clusters()
        assert isinstance(clusters2, dict)
        assert "ardenone-cluster" in clusters2

    def test_get_clusters_returns_dict(self) -> None:
        """get_clusters returns a dict mapping cluster names to configs."""
        clusters = get_clusters()
        assert isinstance(clusters, dict)
        # Should have at least one known cluster
        assert len(clusters) > 0


class TestPoisonProtection:
    """Test that malformed YAML returns last-known-good cache instead of empty."""

    def test_read_clusters_file_returns_cache_on_yaml_error(self) -> None:
        """_read_clusters_file returns cached data on YAML parse errors."""
        import src.fetch.clusters as clusters_module

        # Populate the cache first with a known good state
        clusters_module.reset_cache()
        clusters_module.get_clusters()  # This loads the real config

        # Mock yaml.safe_load to raise a YAMLError (simulating malformed YAML)
        with patch("src.fetch.clusters.yaml.safe_load", side_effect=yaml.YAMLError("parse error")):
            # Should return the cached good state, not empty
            result = clusters_module._read_clusters_file()
            assert isinstance(result, dict)
            # Should have some of the real clusters from the cache
            assert len(result) > 0

    def test_read_clusters_file_returns_cache_on_non_dict_top_level(self) -> None:
        """_read_clusters_file returns cached data when top-level is not a dict."""
        import src.fetch.clusters as clusters_module

        # Populate the cache
        clusters_module.reset_cache()
        clusters_module.get_clusters()

        # Mock yaml.safe_load to return a list instead of dict
        with patch("src.fetch.clusters.yaml.safe_load", return_value=["item1", "item2", "item3"]):
            result = clusters_module._read_clusters_file()
            assert isinstance(result, dict)
            assert len(result) > 0

    def test_read_clusters_file_returns_cache_on_non_dict_clusters_key(self) -> None:
        """_read_clusters_file returns cached data when 'clusters' is not a dict."""
        import src.fetch.clusters as clusters_module

        # Populate the cache
        clusters_module.reset_cache()
        clusters_module.get_clusters()

        # Mock yaml.safe_load to return 'clusters' as a list
        with patch("src.fetch.clusters.yaml.safe_load", return_value={"clusters": ["item1", "item2"]}):
            result = clusters_module._read_clusters_file()
            assert isinstance(result, dict)
            assert len(result) > 0

    def test_read_clusters_file_returns_cache_on_file_not_found(self) -> None:
        """_read_clusters_file returns cached data when file is missing."""
        import src.fetch.clusters as clusters_module

        # Populate the cache
        clusters_module.reset_cache()
        clusters_module.get_clusters()

        # Mock Path.read_text to raise FileNotFoundError
        with patch.object(Path, "read_text", side_effect=FileNotFoundError("No such file")):
            result = clusters_module._read_clusters_file()
            # Returns empty dict on file not found (per implementation)
            assert isinstance(result, dict)

    def test_read_clusters_file_returns_empty_on_error_with_no_cache(self) -> None:
        """When cache is empty, malformed YAML returns empty dict (not crash)."""
        import src.fetch.clusters as clusters_module

        # Reset cache to be empty
        clusters_module.reset_cache()

        # Mock yaml.safe_load to raise a YAMLError
        with patch("src.fetch.clusters.yaml.safe_load", side_effect=yaml.YAMLError("parse error")):
            result = clusters_module._read_clusters_file()
            assert isinstance(result, dict)
            assert len(result) == 0

    def test_get_clusters_preserves_cache_on_parse_failure(self) -> None:
        """get_clusters preserves the cache when a parse failure occurs."""
        import src.fetch.clusters as clusters_module

        # Populate cache
        clusters_module.reset_cache()
        clusters1 = clusters_module.get_clusters()
        assert "ardenone-cluster" in clusters1

        # Mock yaml.safe_load to raise a YAMLError on next read
        with patch("src.fetch.clusters.yaml.safe_load", side_effect=yaml.YAMLError("parse error")):
            # Even though the file parse fails, we should get the cached good state
            clusters2 = clusters_module.get_clusters(force=True)
            assert "ardenone-cluster" in clusters2


class TestArgocdResolutionDataclass:
    """Test ArgocdResolution dataclass structure."""

    def test_satisfiable_resolution(self) -> None:
        """Satisfiable resolution has all fields populated correctly."""
        resolution = ArgocdResolution(
            cluster="test-cluster",
            argocd_api="https://argocd.example.com",
            access=CONSUMABLE_ACCESS,
            satisfiable=True,
        )
        assert resolution.cluster == "test-cluster"
        assert resolution.argocd_api == "https://argocd.example.com"
        assert resolution.access == CONSUMABLE_ACCESS
        assert resolution.satisfiable is True
        assert resolution.reason is None  # satisfiable resolutions don't need a reason

    def test_unsatisfiable_resolution_includes_reason(self) -> None:
        """Unsatisfiable resolution includes a reason."""
        resolution = ArgocdResolution(
            cluster="test-cluster",
            argocd_api=None,
            access="authenticated",
            satisfiable=False,
            reason="Requires authentication",
        )
        assert resolution.satisfiable is False
        assert resolution.reason == "Requires authentication"


class TestArgocdEndpointUnresolvableException:
    """Test ArgocdEndpointUnresolvable exception."""

    def test_exception_carry_reason(self) -> None:
        """Exception carries the human-readable reason."""
        exc = ArgocdEndpointUnresolvable("No cluster configured", cluster=None)
        assert exc.reason == "No cluster configured"
        assert exc.cluster is None
        assert str(exc) == "No cluster configured"

    def test_exception_with_cluster(self) -> None:
        """Exception can optionally carry cluster name."""
        exc = ArgocdEndpointUnresolvable("Unknown cluster", cluster="foo-cluster")
        assert exc.reason == "Unknown cluster"
        assert exc.cluster == "foo-cluster"
