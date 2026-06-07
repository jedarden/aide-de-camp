"""
CLI configuration management.

Handles loading and storing configuration including server URL, session ID, and other
CLI preferences. Configuration is stored in ~/.config/adc/config.
"""

import os
from pathlib import Path
from typing import Optional


class Config:
    """CLI configuration manager."""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "adc"
        self.config_file = self.config_dir / "config"
        self._server_url: Optional[str] = None
        self._session_id: Optional[str] = None

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
        self._server_url = url
        self.ensure_config_dir()

        # Read existing config
        existing_lines = []
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                existing_lines = f.readlines()

        # Update or add server_url
        updated = False
        new_lines = []
        for line in existing_lines:
            if line.startswith("server_url"):
                new_lines.append(f'server_url = "{url}"\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f'server_url = "{url}"\n')

        # Write back
        with open(self.config_file, "w") as f:
            f.writelines(new_lines)

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
        self._session_id = session_id
        self.ensure_config_dir()

        # Read existing config
        existing_lines = []
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                existing_lines = f.readlines()

        # Update or add session_id
        updated = False
        new_lines = []
        for line in existing_lines:
            if line.startswith("session_id"):
                new_lines.append(f'session_id = "{session_id}"\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f'session_id = "{session_id}"\n')

        # Write back
        with open(self.config_file, "w") as f:
            f.writelines(new_lines)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
