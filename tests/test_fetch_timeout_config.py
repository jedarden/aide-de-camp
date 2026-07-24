"""
Tests for per-source timeout configuration (bead adc-33xez).

Tests the config/fetch.yaml timeout configuration system:
- Loading and parsing timeout_ms values
- Validation of timeout values (positive integers only)
- Default behavior when timeout not specified
- Project-specific overrides
- Integration with fetch orchestrator
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.fetch.commands import (
    FetchCommandSpec,
    FetchConfigValidationError,
    FetchSource,
    get_effective_timeout,
    get_source_timeout_ms,
    _validate_timeout_ms,
    _load_fetch_config,
)


class TestValidateTimeoutMs:
    """Tests for _validate_timeout_ms function."""

    def test_validate_positive_integer(self):
        """Positive integer timeout_ms should be validated."""
        result = _validate_timeout_ms(5000, "test_source")
        assert result == 5  # 5000ms = 5 seconds

    def test_validate_positive_float(self):
        """Positive float timeout_ms should be converted to int seconds."""
        result = _validate_timeout_ms(5500.5, "test_source")
        assert result == 5.5  # 5500.5ms = 5.5 seconds

    def test_validate_none_returns_none(self):
        """None timeout_ms should return None (no timeout)."""
        result = _validate_timeout_ms(None, "test_source")
        assert result is None

    def test_validate_zero_raises_error(self):
        """Zero timeout_ms should raise validation error."""
        with pytest.raises(FetchConfigValidationError) as exc_info:
            _validate_timeout_ms(0, "test_source")
        assert "must be positive" in str(exc_info.value)

    def test_validate_negative_raises_error(self):
        """Negative timeout_ms should raise validation error."""
        with pytest.raises(FetchConfigValidationError) as exc_info:
            _validate_timeout_ms(-1000, "test_source")
        assert "must be positive" in str(exc_info.value)

    def test_validate_string_raises_error(self):
        """String timeout_ms should raise validation error."""
        with pytest.raises(FetchConfigValidationError) as exc_info:
            _validate_timeout_ms("5000", "test_source")
        assert "must be a number" in str(exc_info.value)

    def test_validate_list_raises_error(self):
        """List timeout_ms should raise validation error."""
        with pytest.raises(FetchConfigValidationError) as exc_info:
            _validate_timeout_ms([5000], "test_source")
        assert "must be a number" in str(exc_info.value)


class TestLoadFetchConfig:
    """Tests for _load_fetch_config function."""

    def test_load_nonexistent_file_returns_empty_dict(self, tmp_path):
        """Nonexistent config file should return empty dict."""
        with patch('src.fetch.commands.FETCH_CONFIG_PATH', tmp_path / "nonexistent.yaml"):
            config = _load_fetch_config()
            assert config == {}

    def test_load_valid_config(self, tmp_path):
        """Valid config file should be loaded correctly."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 5000
  git_log:
    timeout_ms: 3000

project_timeouts:
  test-project:
    kubectl_pods:
      timeout_ms: 10000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            config = _load_fetch_config()
            assert config["sources"]["kubectl_pods"]["timeout_ms"] == 5000
            assert config["sources"]["git_log"]["timeout_ms"] == 3000
            assert config["project_timeouts"]["test-project"]["kubectl_pods"]["timeout_ms"] == 10000

    def test_load_config_with_invalid_timeout_raises_error(self, tmp_path):
        """Config with invalid timeout_ms should raise validation error."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: -5000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            with pytest.raises(FetchConfigValidationError) as exc_info:
                _load_fetch_config()
            assert "must be positive" in str(exc_info.value)

    def test_load_config_with_invalid_sources_type_raises_error(self, tmp_path):
        """Config with non-dict sources should raise validation error."""
        config_content = """
sources: "not_a_dict"
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            with pytest.raises(FetchConfigValidationError) as exc_info:
                _load_fetch_config()
            assert "must be a dictionary" in str(exc_info.value)

    def test_load_config_with_invalid_source_entry_raises_error(self, tmp_path):
        """Config with non-dict source entry should raise validation error."""
        config_content = """
sources:
  kubectl_pods: "not_a_dict"
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            with pytest.raises(FetchConfigValidationError) as exc_info:
                _load_fetch_config()
            assert "must be a dictionary" in str(exc_info.value)


class TestGetSourceTimeoutMs:
    """Tests for get_source_timeout_ms function."""

    def test_get_timeout_from_config(self, tmp_path):
        """Should return timeout from config when specified."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 8000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            timeout = get_source_timeout_ms(FetchSource.KUBECTL_PODS)
            assert timeout == 8.0  # 8000ms = 8 seconds

    def test_get_timeout_returns_none_when_not_specified(self, tmp_path):
        """Should return None when timeout not in config."""
        config_content = """
sources:
  git_log:
    timeout_ms: 3000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            timeout = get_source_timeout_ms(FetchSource.KUBECTL_PODS)
            assert timeout is None

    def test_get_project_specific_timeout_override(self, tmp_path):
        """Should use project-specific override when available."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 5000

project_timeouts:
  options-pipeline:
    kubectl_pods:
      timeout_ms: 15000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            # Default timeout
            timeout_default = get_source_timeout_ms(FetchSource.KUBECTL_PODS)
            assert timeout_default == 5.0

            # Project-specific override
            timeout_override = get_source_timeout_ms(FetchSource.KUBECTL_PODS, "options-pipeline")
            assert timeout_override == 15.0

    def test_get_timeout_handles_null_value(self, tmp_path):
        """Should handle null timeout_ms in config."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: null
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            timeout = get_source_timeout_ms(FetchSource.KUBECTL_PODS)
            assert timeout is None

    def test_get_timeout_with_invalid_config_returns_none(self, tmp_path):
        """Should return None when config is invalid (graceful degradation)."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: -1000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            # Should return None on validation error (graceful degradation)
            timeout = get_source_timeout_ms(FetchSource.KUBECTL_PODS)
            assert timeout is None


class TestGetEffectiveTimeout:
    """Tests for get_effective_timeout function."""

    def test_effective_timeout_from_config(self, tmp_path):
        """Should use timeout from config when available."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 7000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            spec = FetchCommandSpec(
                source=FetchSource.KUBECTL_PODS,
                command_template="kubectl get pods",
                timeout_seconds=5,
            )
            timeout = get_effective_timeout(spec)
            assert timeout == 7.0  # Config override (7000ms)

    def test_effective_timeout_falls_back_to_spec_default(self, tmp_path):
        """Should fall back to spec timeout_seconds when not in config."""
        config_content = """
sources:
  git_log:
    timeout_ms: 3000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            spec = FetchCommandSpec(
                source=FetchSource.KUBECTL_PODS,
                command_template="kubectl get pods",
                timeout_seconds=10,
            )
            timeout = get_effective_timeout(spec)
            assert timeout == 10  # Spec default

    def test_effective_timeout_infinity_when_none(self, tmp_path):
        """Should return infinity when neither config nor spec specifies timeout."""
        config_content = """
sources: {}
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            spec = FetchCommandSpec(
                source=FetchSource.KUBECTL_PODS,
                command_template="kubectl get pods",
                timeout_seconds=None,
            )
            timeout = get_effective_timeout(spec)
            assert timeout == float('inf')

    def test_effective_timeout_with_project_override(self, tmp_path):
        """Should use project-specific override from config."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 5000

project_timeouts:
  kalshi-tape:
    kubectl_pods:
      timeout_ms: 12000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            spec = FetchCommandSpec(
                source=FetchSource.KUBECTL_PODS,
                command_template="kubectl get pods",
                timeout_seconds=5,
            )

            # Without project slug - uses default
            timeout_default = get_effective_timeout(spec)
            assert timeout_default == 5.0

            # With project slug - uses override
            timeout_override = get_effective_timeout(spec, "kalshi-tape")
            assert timeout_override == 12.0


class TestConfigCaching:
    """Tests for config file caching behavior."""

    def test_config_caches_on_multiple_loads(self, tmp_path):
        """Config should be cached and not reloaded on subsequent calls."""
        config_content = """
sources:
  kubectl_pods:
    timeout_ms: 4000
"""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text(config_content)

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            # First load
            config1 = _load_fetch_config()
            cache_mtime1 = commands_module._fetch_config_mtime

            # Second load - should use cache
            config2 = _load_fetch_config()
            cache_mtime2 = commands_module._fetch_config_mtime

            assert config1 is config2  # Same object (cached)
            assert cache_mtime1 == cache_mtime2

    def test_config_reloads_on_file_change(self, tmp_path):
        """Config should reload when file modification time changes."""
        config_file = tmp_path / "fetch.yaml"
        config_file.write_text("""
sources:
  kubectl_pods:
    timeout_ms: 4000
""")

        with patch('src.fetch.commands.FETCH_CONFIG_PATH', config_file):
            # Clear cache to force reload
            import src.fetch.commands as commands_module
            commands_module._fetch_config_cache = None
            commands_module._fetch_config_mtime = 0

            # First load
            config1 = _load_fetch_config()
            assert config1["sources"]["kubectl_pods"]["timeout_ms"] == 4000

            # Update file
            import time
            time.sleep(0.01)  # Ensure different mtime
            config_file.write_text("""
sources:
  kubectl_pods:
    timeout_ms: 9000
""")

            # Second load - should detect mtime change and reload
            config2 = _load_fetch_config()
            assert config2["sources"]["kubectl_pods"]["timeout_ms"] == 9000
