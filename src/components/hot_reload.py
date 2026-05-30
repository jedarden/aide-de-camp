"""
Hot-reload infrastructure for aide-de-camp.

Provides per-invocation reload for all artifacts (prompts, configs).
Each file is checked for mtime changes and reloaded if modified.
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import yaml


@dataclass
class Artifact:
    """A hot-reloadable artifact."""
    path: Path
    content: str
    mtime: float
    last_check: float


class HotReloadManager:
    """
    Manages hot-reload for all artifacts.

    Usage:
        reload_mgr = HotReloadManager()

        # Register artifacts
        reload_mgr.register_prompt('router', 'prompts/router.md')
        reload_mgr.register_config('registry', 'config/registry.yaml')

        # Get current content (auto-reloads if changed)
        router_prompt = reload_mgr.get_prompt('router')
        registry_config = reload_mgr.get_config('registry')
    """

    CHECK_INTERVAL = 1.0  # Seconds between mtime checks

    def __init__(self):
        self._artifacts: Dict[str, Artifact] = {}
        self._cache: Dict[str, Any] = {}  # Parsed content cache
        self._parsers: Dict[str, Callable[[str], Any]] = {
            '.md': lambda x: x,
            '.yaml': self._parse_yaml,
            '.yml': self._parse_yaml,
        }

    @staticmethod
    def _parse_yaml(content: str) -> Any:
        """Parse YAML content."""
        return yaml.safe_load(content)

    def register_prompt(self, name: str, path: str):
        """
        Register a prompt artifact for hot-reload.

        Args:
            name: Artifact name (e.g., 'router', 'synthesize')
            path: Path to the prompt file
        """
        full_path = Path(path).expanduser().absolute()
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        mtime = full_path.stat().st_mtime
        with open(full_path) as f:
            content = f.read()

        self._artifacts[name] = Artifact(
            path=full_path,
            content=content,
            mtime=mtime,
            last_check=time.time()
        )
        self._cache[name] = content

    def register_config(self, name: str, path: str):
        """
        Register a config artifact for hot-reload.

        Args:
            name: Artifact name (e.g., 'registry', 'monitoring')
            path: Path to the config file
        """
        full_path = Path(path).expanduser().absolute()
        if not full_path.exists():
            raise FileNotFoundError(f"Config file not found: {full_path}")

        mtime = full_path.stat().st_mtime
        with open(full_path) as f:
            content = f.read()

        # Parse based on extension
        suffix = full_path.suffix.lower()
        parser = self._parsers.get(suffix)
        if parser is None:
            raise ValueError(f"Unsupported file type: {suffix}")

        parsed = parser(content)

        self._artifacts[name] = Artifact(
            path=full_path,
            content=content,
            mtime=mtime,
            last_check=time.time()
        )
        self._cache[name] = parsed

    def _check_and_reload(self, name: str) -> bool:
        """
        Check if an artifact needs reloading and reload if so.

        Returns:
            True if reloaded, False otherwise
        """
        if name not in self._artifacts:
            return False

        artifact = self._artifacts[name]
        now = time.time()

        # Throttle checks
        if now - artifact.last_check < self.CHECK_INTERVAL:
            return False

        # Check mtime
        current_mtime = artifact.path.stat().st_mtime
        if current_mtime <= artifact.mtime:
            artifact.last_check = now
            return False

        # Reload
        with open(artifact.path) as f:
            new_content = f.read()

        artifact.content = new_content
        artifact.mtime = current_mtime
        artifact.last_check = now

        # Parse and cache
        suffix = artifact.path.suffix.lower()
        parser = self._parsers.get(suffix)
        if parser:
            self._cache[name] = parser(new_content)
        else:
            self._cache[name] = new_content

        return True

    def get_prompt(self, name: str) -> str:
        """
        Get a prompt's content, reloading if changed.

        Args:
            name: The prompt artifact name

        Returns:
            The prompt content as a string
        """
        self._check_and_reload(name)
        return self._cache[name]

    def get_config(self, name: str) -> Any:
        """
        Get a config's parsed content, reloading if changed.

        Args:
            name: The config artifact name

        Returns:
            The parsed config (dict for YAML)
        """
        self._check_and_reload(name)
        return self._cache[name]

    def force_reload(self, name: str):
        """
        Force reload an artifact, bypassing the mtime check.

        Useful after manual edits or in tests.
        """
        if name not in self._artifacts:
            raise KeyError(f"Unknown artifact: {name}")

        artifact = self._artifacts[name]

        with open(artifact.path) as f:
            new_content = f.read()

        artifact.content = new_content
        artifact.mtime = artifact.path.stat().st_mtime
        artifact.last_check = time.time()

        # Parse and cache
        suffix = artifact.path.suffix.lower()
        parser = self._parsers.get(suffix)
        if parser:
            self._cache[name] = parser(new_content)
        else:
            self._cache[name] = new_content

    def get_mtime(self, name: str) -> Optional[float]:
        """Get the current mtime of an artifact."""
        if name in self._artifacts:
            return self._artifacts[name].mtime
        return None

    def list_artifacts(self) -> Dict[str, str]:
        """List all registered artifacts and their paths."""
        return {
            name: str(artifact.path)
            for name, artifact in self._artifacts.items()
        }


# Singleton instance for the application
_reload_manager: Optional[HotReloadManager] = None


def get_reload_manager() -> HotReloadManager:
    """Get or create the hot-reload manager singleton."""
    global _reload_manager
    if _reload_manager is None:
        _reload_manager = HotReloadManager()
        _reload_manager.register_prompt('router', 'prompts/router.md')
        _reload_manager.register_prompt('synthesize', 'prompts/synthesize.md')
        _reload_manager.register_prompt('voice', 'prompts/voice.md')
        _reload_manager.register_prompt('urgency', 'prompts/urgency.md')
        _reload_manager.register_prompt('fetch_status', 'prompts/fetch/status.md')
        _reload_manager.register_prompt('fetch_action', 'prompts/fetch/action.md')
        _reload_manager.register_config('registry', 'config/registry.yaml')
        _reload_manager.register_config('monitoring', 'config/monitoring.yaml')
        _reload_manager.register_config('exceptions', 'config/exceptions.yaml')
    return _reload_manager
