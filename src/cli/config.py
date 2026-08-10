"""
CLI configuration management.

Handles loading and storing configuration including server URL, session ID, and other
CLI preferences. Configuration is stored in ~/.config/adc/config.
"""

import os
import threading
from pathlib import Path
from typing import Optional

from src.utils.atomic_write import atomic_write


class Config:
    """CLI configuration manager."""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "adc"
        self.config_file = self.config_dir / "config"
        self._server_url: Optional[str] = None
        self._session_id: Optional[str] = None
        self._config_lock = threading.RLock()

    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_server_url(self) -> str:
        """Get the server URL from config or environment variable."""
        if self._server_url:
            return self._server_url

        # Check environment variable first
        env_url = os.getenv("ADC_SERVER_URL")
        if env_url:
            self._server_url = env_url
            return env_url

        # Check config file
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                for line in f:
                    if line.startswith("server_url"):
                        # Parse: server_url = "http://localhost:8000"
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            self._server_url = parts[1].strip().strip('"').strip("'")
                            return self._server_url

        # Default to localhost for Phase 0
        return "http://localhost:8000"

    def set_server_url(self, url: str) -> None:
        """Set the server URL in config."""
        with self._config_lock:
            self._rewrite_value("server_url", url)
            self._server_url = url

    def get_session_id(self) -> Optional[str]:
        """Get the session ID from config."""
        if self._session_id:
            return self._session_id

        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                for line in f:
                    if line.startswith("session_id"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            self._session_id = parts[1].strip().strip('"').strip("'")
                            return self._session_id

        return None

    def set_session_id(self, session_id: str) -> None:
        """Set the session ID in config."""
        with self._config_lock:
            self._rewrite_value("session_id", session_id)
            self._session_id = session_id

    def _rewrite_value(self, key: str, value: str) -> None:
        """Replace one setting in a complete config snapshot (F-06/F-07)."""
        self.ensure_config_dir()
        existing_lines = self.config_file.read_text().splitlines(keepends=True) if self.config_file.exists() else []
        replacement = f'{key} = "{value}"\n'
        new_lines = [replacement if line.startswith(key) else line for line in existing_lines]
        if not any(line.startswith(key) for line in existing_lines):
            new_lines.append(replacement)
        # Atomic replace is the commit point; in-memory state is published only
        # after the complete config snapshot is durable.
        atomic_write(self.config_file, ''.join(new_lines))


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
