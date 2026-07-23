"""
Tests for monitoring configuration hot-reload functionality.

Tests cover:
- Config loading with mtime-based cache
- File modification detection and auto-reload
- Cache invalidation
- Tick interval configuration
- Integration with AmbientMonitor
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from src.monitoring.config_loader import ConfigLoader, get_monitoring_config_loader
from src.monitoring.ambient import AmbientMonitor, get_ambient_monitor


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_data = {
            'tick_interval_seconds': 300,
            'monitoring': {
                'active_topics': [
                    {
                        'topic_id': 'test-topic',
                        'project_slug': 'test-project',
                        'intent_type': 'status',
                        'check_interval': 60,
                        'urgency': 'normal',
                        'filters': [],
                        'notification_threshold': 'any_change',
                    }
                ],
                'exceptions': [],
                'batching': {
                    'low_urgency_batch_seconds': 300,
                    'normal_urgency_batch_seconds': 120,
                },
                'quiet_hours': {
                    'enabled': False,
                    'start': '22:00',
                    'end': '08:00',
                    'timezone': 'America/New_York',
                },
                'channels': {
                    'critical': ['canvas', 'telegram'],
                    'high': ['canvas'],
                    'normal': ['canvas'],
                    'low': ['canvas'],
                },
            },
        }
        yaml.dump(config_data, f)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def config_loader(temp_config_file):
    """Create a ConfigLoader instance for testing."""
    return ConfigLoader(config_path=temp_config_file, default_tick_interval_seconds=300)


class TestConfigLoader:
    """Tests for ConfigLoader hot-reload functionality."""

    @pytest.mark.asyncio
    async def test_initial_load(self, config_loader):
        """Test initial configuration loading."""
        config = await config_loader.get_config()

        assert config is not None
        assert 'tick_interval_seconds' in config
        assert config['tick_interval_seconds'] == 300
        assert 'monitoring' in config
        assert len(config['monitoring']['active_topics']) == 1

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_access(self, config_loader):
        """Test that second access uses cache (no file modification)."""
        # First access - loads from disk
        config1 = await config_loader.get_config()
        first_cache = config_loader._cache

        # Second access - should use cache
        config2 = await config_loader.get_config()
        second_cache = config_loader._cache

        # Config should be the same
        assert config1 == config2

        # Cache should be the same object (not reloaded)
        assert first_cache is second_cache
        assert first_cache.mtime == second_cache.mtime
        assert first_cache.loaded_at == second_cache.loaded_at

    @pytest.mark.asyncio
    async def test_file_modification_detection(self, temp_config_file):
        """Test that file modification triggers reload."""
        loader = ConfigLoader(config_path=temp_config_file, default_tick_interval_seconds=300)

        # Initial load
        config1 = await loader.get_config()
        initial_mtime = loader._cache.mtime

        # Wait to ensure mtime difference
        await asyncio.sleep(0.1)

        # Modify the config file
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['tick_interval_seconds'] = 600

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        # Force mtime update (some filesystems have coarse granularity)
        import os
        os.utime(temp_config_file, None)

        # Get config again - should detect modification and reload
        config2 = await loader.get_config()

        # Config should have new value
        assert config2['tick_interval_seconds'] == 600

        # Cache should have new mtime
        assert loader._cache.mtime != initial_mtime

    @pytest.mark.asyncio
    async def test_force_reload(self, config_loader):
        """Test force reload parameter bypasses cache."""
        # Initial load
        await config_loader.get_config()
        initial_cache = config_loader._cache

        # Force reload
        await config_loader.get_config(force_reload=True)

        # Cache should be different (reloaded)
        assert config_loader._cache is not initial_cache
        assert config_loader._cache.mtime == initial_cache.mtime  # Same file, same mtime

    @pytest.mark.asyncio
    async def test_get_tick_interval_seconds(self, config_loader):
        """Test getting tick interval from config."""
        # Get from config
        interval = await config_loader.get_tick_interval_seconds()
        assert interval == 300

    @pytest.mark.asyncio
    async def test_get_tick_interval_seconds_default(self, temp_config_file):
        """Test default tick interval when not in config."""
        # Create config without tick_interval_seconds
        with open(temp_config_file, 'w') as f:
            yaml.dump({'monitoring': {'active_topics': []}}, f)

        loader = ConfigLoader(
            config_path=temp_config_file,
            default_tick_interval_seconds=600,
        )

        interval = await loader.get_tick_interval_seconds()
        assert interval == 600

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, config_loader):
        """Test cache invalidation."""
        # Load config
        await config_loader.get_config()
        assert config_loader.is_cached()

        # Invalidate cache
        await config_loader.invalidate_cache()
        assert config_loader._cache is None
        assert not config_loader.is_cached()

        # Next access should reload
        await config_loader.get_config()
        assert config_loader.is_cached()

    def test_cache_age(self, config_loader):
        """Test cache age calculation."""
        import asyncio

        # Not cached yet
        assert config_loader.cache_age_seconds is None

        # Run async test
        async def run_test():
            await config_loader.get_config()
            age = config_loader.cache_age_seconds

            assert age is not None
            assert age >= 0
            assert age < 1  # Should be very recent

            # Wait and check age increased
            await asyncio.sleep(0.1)
            new_age = config_loader.cache_age_seconds

            assert new_age > age

        asyncio.run(run_test())

    @pytest.mark.asyncio
    async def test_concurrent_access(self, config_loader):
        """Test concurrent accesses are handled safely."""
        # Access config concurrently
        tasks = [config_loader.get_config() for _ in range(10)]
        configs = await asyncio.gather(*tasks)

        # All should return the same config
        assert all(c == configs[0] for c in configs)

        # Cache should be consistent
        assert config_loader._cache is not None


class TestGlobalConfigLoader:
    """Tests for global config loader instance."""

    @pytest.mark.asyncio
    async def test_global_singleton(self):
        """Test that get_monitoring_config_loader returns singleton."""
        loader1 = get_monitoring_config_loader()
        loader2 = get_monitoring_config_loader()

        assert loader1 is loader2

    @pytest.mark.asyncio
    async def test_global_loader_with_custom_path(self, temp_config_file):
        """Test global loader with custom path."""
        loader = get_monitoring_config_loader(config_path=temp_config_file)

        config = await loader.get_config()
        assert config is not None


class TestAmbientMonitorIntegration:
    """Tests for AmbientMonitor integration with hot-reload."""

    @pytest.mark.asyncio
    async def test_ambient_monitor_uses_config_loader(self, temp_config_file):
        """Test that AmbientMonitor uses the hot-reload config loader."""
        monitor = AmbientMonitor(config_path=temp_config_file)

        # Monitor should have config loader
        assert monitor._config_loader is not None
        assert monitor._config_loader.config_path == temp_config_file

        # Load config should use config loader
        config = await monitor.load_config()

        assert config is not None
        assert len(config.active_topics) == 1
        assert config.active_topics[0].topic_id == 'test-topic'

    @pytest.mark.asyncio
    async def test_ambient_monitor_config_changes(self, temp_config_file):
        """Test that AmbientMonitor responds to config changes."""
        monitor = AmbientMonitor(config_path=temp_config_file)

        # Initial config
        config1 = await monitor.load_config()
        assert len(config1.active_topics) == 1

        # Wait to ensure mtime difference
        await asyncio.sleep(0.1)

        # Modify config to add a new topic
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['monitoring']['active_topics'].append({
            'topic_id': 'new-topic',
            'project_slug': 'new-project',
            'intent_type': 'status',
            'check_interval': 120,
            'urgency': 'high',
            'filters': [],
            'notification_threshold': 'state_change',
        })

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        # Force mtime update
        import os
        os.utime(temp_config_file, None)

        # Reload config
        await monitor.reload_config()
        config2 = await monitor.load_config()

        # Should have new topic
        assert len(config2.active_topics) == 2
        topic_ids = {t.topic_id for t in config2.active_topics}
        assert 'new-topic' in topic_ids

    @pytest.mark.asyncio
    async def test_ambient_monitor_start_creates_ticker(self, temp_config_file):
        """Test that starting AmbientMonitor creates a ticker task."""
        monitor = AmbientMonitor(config_path=temp_config_file)

        # Start monitoring
        await monitor.start()

        # Should have ticker task
        assert monitor._ticker_task is not None
        assert monitor._ticker_task in monitor.tasks

        # Stop monitoring
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_config_ticker_detects_changes(self, temp_config_file):
        """Test that the config ticker detects file changes."""
        # Use a short tick interval for testing
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['tick_interval_seconds'] = 1  # 1 second for testing

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        monitor = AmbientMonitor(config_path=temp_config_file)
        await monitor.start()

        # Wait for ticker to run once
        await asyncio.sleep(1.5)

        # Modify config
        await asyncio.sleep(0.1)
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['monitoring']['active_topics'].append({
            'topic_id': 'detected-topic',
            'project_slug': 'detected-project',
            'intent_type': 'status',
            'check_interval': 120,
            'urgency': 'high',
            'filters': [],
            'notification_threshold': 'state_change',
        })

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        # Force mtime update
        import os
        os.utime(temp_config_file, None)

        # Wait for ticker to detect change
        await asyncio.sleep(1.5)

        # Check that config was reloaded
        config = await monitor.load_config()
        assert len(config.active_topics) >= 2  # At least the new topic

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_get_ambient_monitor_singleton(self):
        """Test that get_ambient_monitor returns singleton."""
        monitor1 = get_ambient_monitor()
        monitor2 = get_ambient_monitor()

        assert monitor1 is monitor2


class TestTickIntervalConfiguration:
    """Tests for tick interval configuration and hot-reload."""

    @pytest.mark.asyncio
    async def test_tick_interval_from_config(self, config_loader):
        """Test reading tick interval from config."""
        interval = await config_loader.get_tick_interval_seconds()
        assert interval == 300

    @pytest.mark.asyncio
    async def test_tick_interval_changes_on_reload(self, temp_config_file):
        """Test that tick interval updates when config changes."""
        loader = ConfigLoader(config_path=temp_config_file, default_tick_interval_seconds=300)

        # Initial interval
        interval1 = await loader.get_tick_interval_seconds()
        assert interval1 == 300

        # Wait to ensure mtime difference
        await asyncio.sleep(0.1)

        # Change tick interval in config
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['tick_interval_seconds'] = 600

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        # Force mtime update
        import os
        os.utime(temp_config_file, None)

        # Get new interval
        interval2 = await loader.get_tick_interval_seconds()
        assert interval2 == 600

    @pytest.mark.asyncio
    async def test_tick_interval_hot_reload_in_monitor(self, temp_config_file):
        """Test that AmbientMonitor ticker uses updated tick interval."""
        # Set initial tick interval to 1 second for testing
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['tick_interval_seconds'] = 1

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        monitor = AmbientMonitor(config_path=temp_config_file)

        # Get initial tick interval
        interval1 = await monitor._config_loader.get_tick_interval_seconds()
        assert interval1 == 1

        # Wait to ensure mtime difference
        await asyncio.sleep(0.1)

        # Change tick interval
        with open(temp_config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        config_data['tick_interval_seconds'] = 2

        with open(temp_config_file, 'w') as f:
            yaml.dump(config_data, f)

        # Force mtime update
        import os
        os.utime(temp_config_file, None)

        # Get new tick interval
        interval2 = await monitor._config_loader.get_tick_interval_seconds()
        assert interval2 == 2


class TestErrorHandling:
    """Tests for error handling in config hot-reload."""

    @pytest.mark.asyncio
    async def test_missing_config_file(self):
        """Test handling of missing config file."""
        loader = ConfigLoader(
            config_path=Path('/nonexistent/config.yaml'),
            default_tick_interval_seconds=300,
        )

        with pytest.raises(FileNotFoundError):
            await loader.get_config()

    @pytest.mark.asyncio
    async def test_invalid_yaml(self, temp_config_file):
        """Test handling of invalid YAML content."""
        # Write invalid YAML
        with open(temp_config_file, 'w') as f:
            f.write("invalid: yaml: content: [unclosed")

        loader = ConfigLoader(config_path=temp_config_file)

        with pytest.raises(yaml.YAMLError):
            await loader.get_config()

    @pytest.mark.asyncio
    async def test_config_loader_handles_concurrent_modifications(self, temp_config_file):
        """Test that config loader handles concurrent file modifications."""
        import os

        loader = ConfigLoader(config_path=temp_config_file)

        # Initial load
        await loader.get_config()

        # Simulate concurrent modifications
        async def modify_config():
            while True:
                await asyncio.sleep(0.05)
                with open(temp_config_file, 'w') as f:
                    yaml.dump({'tick_interval_seconds': 300}, f)
                os.utime(temp_config_file, None)

        # Start modification task
        modify_task = asyncio.create_task(modify_config())

        # Try to read config multiple times
        for _ in range(5):
            await loader.get_config()
            await asyncio.sleep(0.1)

        # Stop modification task
        modify_task.cancel()

        # Final read should still work
        config = await loader.get_config()
        assert config is not None
