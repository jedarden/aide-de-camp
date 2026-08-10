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
import math
import threading
import time
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

import yaml

from ..components.hot_reload import HotReloadTimeoutError

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

    # This is intentionally below five seconds and is the complete budget for
    # one get_config operation, including file I/O and YAML parsing.
    FILE_OPERATION_TIMEOUT = 4.0

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
        self._state_lock = threading.RLock()

    def _get_file_mtime(self) -> float:
        """Get the modification time of the config file."""
        return self.config_path.stat().st_mtime

    def _load_config_file(self) -> dict[str, Any]:
        """Load the configuration file from disk."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def _operation_deadline(self) -> float:
        """Return a monotonic deadline for one config hot-reload operation."""
        try:
            timeout = min(float(self.FILE_OPERATION_TIMEOUT), 4.0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Hot-reload operation configuration failed for path "
                f"'{self.config_path}'. Reason: FILE_OPERATION_TIMEOUT is not "
                "numeric. Action: configure a positive timeout below 5 seconds."
            ) from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(
                "Hot-reload operation configuration failed for path "
                f"'{self.config_path}'. Reason: timeout is not positive. "
                "Action: configure a positive timeout below 5 seconds."
            )
        return time.monotonic() + timeout

    async def _run_with_timeout(
        self,
        operation: str,
        callback,
        deadline: float,
    ):
        """Run synchronous filesystem/parser work in a daemon worker.

        ``asyncio.to_thread`` uses a non-daemon executor and waits for a
        cancelled worker during loop shutdown.  A small daemon thread keeps a
        blocked filesystem call from making a test or request hang forever.
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HotReloadTimeoutError(
                self.config_path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "the operation budget was exhausted before the callback started",
            )

        loop = asyncio.get_running_loop()
        result = loop.create_future()

        def run() -> None:
            try:
                value = callback()
            except BaseException as exc:
                try:
                    loop.call_soon_threadsafe(self._complete_future, result, None, exc)
                except RuntimeError:
                    # The event loop may have closed after the caller timed out.
                    pass
            else:
                try:
                    loop.call_soon_threadsafe(self._complete_future, result, value, None)
                except RuntimeError:
                    pass

        worker = threading.Thread(
            target=run,
            name=f"config-hot-reload-{operation[:24]}",
            daemon=True,
        )
        worker.start()
        try:
            return await asyncio.wait_for(result, timeout=remaining)
        except asyncio.TimeoutError as exc:
            timeout = min(float(self.FILE_OPERATION_TIMEOUT), 4.0)
            raise HotReloadTimeoutError(
                self.config_path,
                operation,
                timeout,
                f"the callback did not finish within the {timeout:.3f}s deadline",
            ) from exc

    @staticmethod
    def _complete_future(future, value, error) -> None:
        """Complete a future if a timed-out daemon worker finishes later."""
        if future.done():
            return
        if error is None:
            future.set_result(value)
        else:
            future.set_exception(error)

    async def _load_config_file_with_timeout(self, deadline: float) -> dict[str, Any]:
        """Read and parse config with contextual, bounded failures."""
        operation = "load monitoring configuration"

        def load() -> dict[str, Any]:
            if not self.config_path.exists():
                raise FileNotFoundError(str(self.config_path))
            with open(self.config_path, "r") as file_handle:
                return yaml.safe_load(file_handle)

        try:
            data = await self._run_with_timeout(operation, load, deadline)
        except HotReloadTimeoutError:
            raise
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: file not found. Action: verify "
                "the configured monitoring file exists and retry."
            ) from exc
        except yaml.YAMLError as exc:
            raise yaml.YAMLError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: invalid YAML: {exc}. Action: "
                "correct the YAML syntax and retry."
            ) from exc
        except OSError as exc:
            raise OSError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: {type(exc).__name__}: {exc}. "
                "Action: check filesystem access and permissions, then retry."
            ) from exc

        if data is None:
            raise ValueError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: configuration is empty. Action: "
                "provide valid YAML data and retry."
            )
        if not isinstance(data, dict):
            raise ValueError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: expected a YAML mapping but "
                f"got {type(data).__name__}. Action: make the configuration "
                "a mapping of named settings and retry."
            )
        return data

    async def _get_file_mtime_with_timeout(self, deadline: float) -> float:
        """Read mtime with context for missing and inaccessible config files."""
        operation = "check monitoring configuration mtime"
        try:
            return await self._run_with_timeout(
                operation,
                self._get_file_mtime,
                deadline,
            )
        except HotReloadTimeoutError:
            raise
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: file not found. Action: verify "
                "the configured monitoring file exists and retry."
            ) from exc
        except OSError as exc:
            raise OSError(
                f"Hot-reload operation '{operation}' failed for path "
                f"'{self.config_path}'. Reason: {type(exc).__name__}: {exc}. "
                "Action: check filesystem access and permissions, then retry."
            ) from exc

    async def _load_with_cache_update(self, deadline: Optional[float] = None) -> CachedConfig:
        """Load config and update cache."""
        deadline = self._operation_deadline() if deadline is None else deadline
        data = await self._load_config_file_with_timeout(deadline)
        mtime = await self._get_file_mtime_with_timeout(deadline)
        loaded_at = time.time()

        cached = CachedConfig(data=data, mtime=mtime, loaded_at=loaded_at)
        with self._state_lock:
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
            FileNotFoundError: If config file doesn't exist.
            HotReloadTimeoutError: If I/O or parsing exceeds four seconds.
        """
        operation = "get monitoring configuration"
        deadline = self._operation_deadline()
        remaining = deadline - time.monotonic()
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=max(remaining, 0))
        except asyncio.TimeoutError as exc:
            raise HotReloadTimeoutError(
                self.config_path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "waiting for another config load to release the async lock",
            ) from exc

        try:
            with self._state_lock:
                cached = self._cache

            # First load - cache is empty
            if cached is None or force_reload:
                cached = await self._load_with_cache_update(deadline)
                return cached.data

            # Check if file has been modified
            current_mtime = await self._get_file_mtime_with_timeout(deadline)

            if current_mtime != cached.mtime:
                logger.info(
                    f"Config file modified (old mtime: {cached.mtime}, "
                    f"new mtime: {current_mtime}), reloading..."
                )
                cached = await self._load_with_cache_update(deadline)
                return cached.data

            # Cache is still valid
            return cached.data
        finally:
            self._lock.release()

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
        operation = "invalidate monitoring configuration cache"
        deadline = self._operation_deadline()
        try:
            await asyncio.wait_for(
                self._lock.acquire(), timeout=max(deadline - time.monotonic(), 0)
            )
        except asyncio.TimeoutError as exc:
            raise HotReloadTimeoutError(
                self.config_path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "waiting for another config load to release the async lock",
            ) from exc
        try:
            with self._state_lock:
                self._cache = None
            logger.debug("Config cache invalidated")
        finally:
            self._lock.release()

    def is_cached(self) -> bool:
        """Check if configuration is currently cached."""
        with self._state_lock:
            return self._cache is not None

    @property
    def cache_age_seconds(self) -> Optional[float]:
        """
        Get the age of the cached configuration in seconds.

        Returns:
            Age in seconds, or None if not cached
        """
        with self._state_lock:
            cached = self._cache
        if cached is None:
            return None

        import time
        return time.time() - cached.loaded_at


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
