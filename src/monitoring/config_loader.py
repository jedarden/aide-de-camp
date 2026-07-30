"""
Hot-reload configuration loader with mtime-based cache.

Caches configuration in memory and checks file modification time (mtime)
on each access. Reloads automatically when the file changes.

This pattern is suitable for:
- Configuration that changes rarely
- Scenarios where the latest config is always needed
- Avoiding file I/O on every read
"""

import asyncio
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

import yaml

logger = getLogger(__name__)


@dataclass
class CachedConfig:
    """Cached configuration with metadata."""
    data: dict[str, Any]
    mtime: float
    loaded_at: float


class ConfigLoader:
    """
    Hot-reload configuration loader with mtime-based cache.

    Monitors a YAML file and automatically reloads when it changes.
    Cache is checked on each access via mtime comparison.
    """

    def __init__(
        self,
        config_path: Path,
        default_tick_interval_seconds: int = 300,
    ):
        """
        Initialize the config loader.

        Args:
            config_path: Path to the YAML configuration file
            default_tick_interval_seconds: Default tick interval if not specified in config
        """
        self.config_path = config_path
        self.default_tick_interval_seconds = default_tick_interval_seconds
        self._cache: Optional[CachedConfig] = None
        self._lock = asyncio.Lock()

    def _get_file_mtime(self) -> float:
        """Get the modification time of the config file."""
        return self.config_path.stat().st_mtime

    def _load_config_file(self) -> dict[str, Any]:
        """Load the configuration file from disk."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    async def _load_with_cache_update(self) -> CachedConfig:
        """Load config and update cache."""
        import time

        data = self._load_config_file()
        mtime = self._get_file_mtime()
        loaded_at = time.time()

        cached = CachedConfig(data=data, mtime=mtime, loaded_at=loaded_at)
        self._cache = cached

        logger.debug(
            f"Config loaded from {self.config_path} "
            f"(mtime: {mtime}, loaded_at: {loaded_at})"
        )

        return cached

    async def get_config(self, force_reload: bool = False) -> dict[str, Any]:
        """
        Get the current configuration, auto-reloading if file has changed.

        Args:
            force_reload: Force reload from disk even if mtime hasn't changed

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        async with self._lock:
            # First load - cache is empty
            if self._cache is None or force_reload:
                cached = await self._load_with_cache_update()
                return cached.data

            # Check if file has been modified
            current_mtime = self._get_file_mtime()

            if current_mtime != self._cache.mtime:
                logger.info(
                    f"Config file modified (old mtime: {self._cache.mtime}, "
                    f"new mtime: {current_mtime}), reloading..."
                )
                cached = await self._load_with_cache_update()
                return cached.data

            # Cache is still valid
            return self._cache.data

    async def get_tick_interval_seconds(self) -> int:
        """
        Get the tick interval from configuration.

        Returns the tick_interval_seconds value from the config,
        or the default if not specified.

        Returns:
            Tick interval in seconds
        """
        config = await self.get_config()
        return config.get(
            "tick_interval_seconds",
            self.default_tick_interval_seconds,
        )

    async def invalidate_cache(self) -> None:
        """Invalidate the cached configuration (force reload on next access)."""
        async with self._lock:
            self._cache = None
            logger.debug("Config cache invalidated")

    def is_cached(self) -> bool:
        """Check if configuration is currently cached."""
        return self._cache is not None

    @property
    def cache_age_seconds(self) -> Optional[float]:
        """
        Get the age of the cached configuration in seconds.

        Returns:
            Age in seconds, or None if not cached
        """
        if self._cache is None:
            return None

        import time
        return time.time() - self._cache.loaded_at


# Global config loader instance for monitoring
_monitoring_config_loader: Optional[ConfigLoader] = None


def get_monitoring_config_loader(
    config_path: Optional[Path] = None,
) -> ConfigLoader:
    """
    Get or create the global monitoring config loader instance.

    Args:
        config_path: Path to monitoring.yaml (uses default if not provided)

    Returns:
        ConfigLoader instance
    """
    global _monitoring_config_loader

    if _monitoring_config_loader is None:
        if config_path is None:
            config_path = Path("/home/coding/aide-de-camp/config/monitoring.yaml")

        _monitoring_config_loader = ConfigLoader(
            config_path=config_path,
            default_tick_interval_seconds=300,
        )

    return _monitoring_config_loader
