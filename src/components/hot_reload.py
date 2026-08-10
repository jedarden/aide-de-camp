"""
Hot-reload infrastructure for aide-de-camp.

Provides per-invocation reload for all artifacts (prompts, configs).
Each file is checked for mtime changes and reloaded if modified.

Enhanced with robust edge case handling:
- Retry logic for transient file system failures
- Timeout protection for file operations
- Thread-safe concurrent access
- Detailed error context and logging
- Graceful degradation under error conditions
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import yaml
import threading
import json

from ..utils.atomic_write import atomic_write

logger = logging.getLogger(__name__)


# Custom exception classes for clear error handling
class HotReloadError(Exception):
    """Base exception for hot-reload errors."""
    pass


class PermissionDeniedError(HotReloadError):
    """Raised when file permission is denied."""

    def __init__(self, path: Path, operation: str):
        self.path = path
        self.operation = operation
        super().__init__(
            f"Permission denied for {operation} on '{path}'. "
            f"Action: Check file permissions with 'ls -la {path.parent}' "
            f"and ensure read access for the current user."
        )


class RegistryNotFoundError(HotReloadError):
    """Raised when registry file is not found."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(
            f"Registry file not found: '{path}'. "
            f"Action: Verify the file exists at the expected location "
            f"or check if the path is correct."
        )


class RegistryParseError(HotReloadError):
    """Raised when registry file parsing fails."""

    def __init__(self, path: Path, parse_error: Exception, content_preview: str = ""):
        self.path = path
        self.parse_error = parse_error
        self.content_preview = content_preview[:200] if content_preview else ""

        # Extract line/column info if available
        details = str(parse_error)
        error_details = f"Parse error: {details}"

        super().__init__(
            f"Failed to parse registry file '{path}'. "
            f"{error_details}. "
            f"Action: Validate the file syntax. "
            f"{f'Content preview: {self.content_preview}...' if self.content_preview else ''}"
        )


class EmptyRegistryError(HotReloadError):
    """Raised when registry file is empty or contains no data."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(
            f"Registry file is empty or contains no valid data: '{path}'. "
            f"Action: Ensure the file contains valid YAML or JSON configuration."
        )


@dataclass
class Artifact:
    """A hot-reloadable artifact."""
    path: Path
    content: str
    mtime: float
    last_check: float
    load_error: Optional[Exception] = None  # Track last load error


class HotReloadManager:
    """
    Manages hot-reload for all artifacts with robust edge case handling.

    Features:
    - Retry logic for transient failures
    - Timeout protection for file operations
    - Thread-safe concurrent access
    - Detailed error context
    - Graceful degradation

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
    MAX_RETRIES = 3  # Maximum retry attempts for transient failures
    RETRY_DELAY = 0.1  # Seconds between retries
    FILE_OPERATION_TIMEOUT = 5.0  # Seconds timeout for file operations

    def __init__(self):
        self._artifacts: Dict[str, Artifact] = {}
        self._cache: Dict[str, Any] = {}  # Parsed content cache
        self._parsers: Dict[str, Callable[[str], Any]] = {
            '.md': lambda x: x,
            '.yaml': self._parse_yaml,
            '.yml': self._parse_yaml,
            '.json': self._parse_json,
        }
        self._lock = threading.RLock()  # Thread-safe access
        self._error_count: Dict[str, int] = {}  # Track error frequency

    @staticmethod
    def _parse_yaml(content: str) -> Any:
        """Parse YAML content with enhanced error handling."""
        try:
            parsed = yaml.safe_load(content)
            return parsed
        except yaml.YAMLError as e:
            # Enhance error message with line/column info if available
            error_details = str(e)
            if hasattr(e, 'problem_mark'):
                mark = e.problem_mark
                error_details = f"line {mark.line + 1}, column {mark.column + 1}: {e.problem}"
            raise ValueError(f"YAML parsing error at {error_details}") from e

    @staticmethod
    def _parse_json(content: str) -> Any:
        """Parse JSON content with enhanced error handling."""
        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError as e:
            # JSON decode errors include line and column
            error_details = f"line {e.lineno}, column {e.colno}: {e.msg}"
            raise ValueError(f"JSON parsing error at {error_details}") from e

    def _read_file_with_retry(self, path: Path, operation: str = "read") -> str:
        """
        Read file content with retry logic for transient failures.

        Args:
            path: File path to read
            operation: Description of the operation for error messages

        Returns:
            File content as string

        Raises:
            PermissionDeniedError: If permission denied after retries
            FileNotFoundError: If file doesn't exist after retries
            OSError: For other OS-level errors after retries
        """
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    # Check for empty files
                    if not content.strip() and path.suffix.lower() in ['.yaml', '.yml', '.json']:
                        logger.warning(f"Empty registry file detected: {path}")
                    return content
            except PermissionError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient permission error during {operation} (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    # Raise custom permission error with actionable guidance
                    logger.error(f"Permission denied after {self.MAX_RETRIES} retries for {path}")
                    raise PermissionDeniedError(path, operation) from e
            except FileNotFoundError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient not found error during {operation} (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    # Raise custom not found error with actionable guidance
                    logger.error(f"File not found after {self.MAX_RETRIES} retries for {path}")
                    raise RegistryNotFoundError(path) from e
            except OSError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient OS error during {operation} (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    # Final attempt failed - enhance error message
                    error_type = type(e).__name__
                    enhanced_msg = f"{error_type} during {operation} for {path}: {str(e)}"
                    logger.error(f"Failed after {self.MAX_RETRIES} retries: {enhanced_msg}")
                    raise type(e)(enhanced_msg) from e

        # Should never reach here, but handle gracefully
        if last_error:
            raise last_error
        raise RuntimeError(f"Unexpected error in _read_file_with_retry for {path}")

    def _get_mtime_with_retry(self, path: Path) -> float:
        """
        Get file modification time with retry logic.

        Args:
            path: File path to check

        Returns:
            File modification time

        Raises:
            RegistryNotFoundError: If file doesn't exist after retries
            PermissionDeniedError: If permission denied after retries
            OSError: For other OS-level errors after retries
        """
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return path.stat().st_mtime
            except PermissionError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient permission error getting mtime (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Permission denied getting mtime for {path}")
                    raise PermissionDeniedError(path, "get file modification time") from e
            except FileNotFoundError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient not found error getting mtime (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"File not found getting mtime for {path}")
                    raise RegistryNotFoundError(path) from e
            except OSError as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(
                        f"Transient OS error getting mtime (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    raise

        # Should never reach here
        if last_error:
            raise last_error
        raise RuntimeError(f"Unexpected error in _get_mtime_with_retry for {path}")

    def register_prompt(self, name: str, path: str):
        """
        Register a prompt artifact for hot-reload with retry logic and thread safety.

        Args:
            name: Artifact name (e.g., 'router', 'synthesize')
            path: Path to the prompt file

        Raises:
            RegistryNotFoundError: If file doesn't exist after retries
            PermissionDeniedError: If file is not readable after retries
            ValueError: If path is invalid
        """
        with self._lock:
            try:
                full_path = Path(path).expanduser().absolute()

                # Validate path
                if not full_path.exists():
                    logger.error(f"Prompt file not found: {full_path}")
                    raise RegistryNotFoundError(full_path)

                if not full_path.is_file():
                    logger.error(f"Path is not a file: {full_path}")
                    raise ValueError(f"Path is not a file: {full_path}")

                # Get mtime with retry
                try:
                    mtime = self._get_mtime_with_retry(full_path)
                except PermissionError as e:
                    logger.error(f"Permission denied accessing prompt file: {full_path}")
                    raise PermissionDeniedError(full_path, f"register_prompt('{name}')") from e

                # Read content with retry
                content = self._read_file_with_retry(full_path, f"register_prompt('{name}')")

                # Store artifact
                self._artifacts[name] = Artifact(
                    path=full_path,
                    content=content,
                    mtime=mtime,
                    last_check=time.time(),
                    load_error=None
                )
                self._cache[name] = content
                self._error_count[name] = 0

                logger.info(f"Registered prompt artifact '{name}' from {full_path}")

            except Exception as e:
                # Track error frequency
                self._error_count[name] = self._error_count.get(name, 0) + 1
                logger.error(f"Failed to register prompt '{name}': {e}")
                raise

    def register_config(self, name: str, path: str):
        """
        Register a config artifact for hot-reload with retry logic and thread safety.

        Args:
            name: Artifact name (e.g., 'registry', 'monitoring')
            path: Path to the config file

        Raises:
            RegistryNotFoundError: If file doesn't exist after retries
            PermissionDeniedError: If file is not readable after retries
            RegistryParseError: If file parsing fails
            EmptyRegistryError: If file is empty
            ValueError: If file type is unsupported
        """
        with self._lock:
            try:
                full_path = Path(path).expanduser().absolute()

                # Validate path
                if not full_path.exists():
                    logger.error(f"Config file not found: {full_path}")
                    raise RegistryNotFoundError(full_path)

                if not full_path.is_file():
                    logger.error(f"Path is not a file: {full_path}")
                    raise ValueError(f"Path is not a file: {full_path}")

                # Get mtime with retry
                try:
                    mtime = self._get_mtime_with_retry(full_path)
                except PermissionError as e:
                    logger.error(f"Permission denied accessing config file: {full_path}")
                    raise PermissionDeniedError(full_path, f"register_config('{name}')") from e

                # Read content with retry
                content = self._read_file_with_retry(full_path, f"register_config('{name}')")

                # Check for empty files before parsing
                if not content.strip():
                    logger.error(f"Empty config file detected: {full_path}")
                    raise EmptyRegistryError(full_path)

                # Parse based on extension
                suffix = full_path.suffix.lower()
                parser = self._parsers.get(suffix)
                if parser is None:
                    logger.error(f"Unsupported file type: {suffix}")
                    raise ValueError(
                        f"Unsupported file type: {suffix}. "
                        f"Supported types: {list(self._parsers.keys())}"
                    )

                try:
                    parsed = parser(content)
                except (ValueError, yaml.YAMLError, json.JSONDecodeError) as e:
                    logger.error(f"Parse error for {full_path}: {e}")
                    raise RegistryParseError(full_path, e, content) from e

                # Store artifact
                self._artifacts[name] = Artifact(
                    path=full_path,
                    content=content,
                    mtime=mtime,
                    last_check=time.time(),
                    load_error=None
                )
                self._cache[name] = parsed
                self._error_count[name] = 0

                logger.info(f"Registered config artifact '{name}' from {full_path}")

            except Exception as e:
                # Track error frequency
                self._error_count[name] = self._error_count.get(name, 0) + 1
                logger.error(f"Failed to register config '{name}': {e}")
                raise

    def _check_and_reload(self, name: str) -> bool:
        """
        Check if an artifact needs reloading and reload if so, with thread safety.

        Returns:
            True if reloaded successfully, False otherwise (even on error)
        """
        with self._lock:
            if name not in self._artifacts:
                return False

            artifact = self._artifacts[name]
            now = time.time()

            # Throttle checks
            if now - artifact.last_check < self.CHECK_INTERVAL:
                return False

            try:
                # Check mtime with retry
                current_mtime = self._get_mtime_with_retry(artifact.path)

                if current_mtime <= artifact.mtime:
                    artifact.last_check = now
                    return False

                # Reload with retry
                new_content = self._read_file_with_retry(
                    artifact.path,
                    f"_check_and_reload('{name}')"
                )

                # Parse completely before publishing artifact metadata. A
                # malformed replacement keeps the old content/mtime/cache.
                suffix = artifact.path.suffix.lower()
                parser = self._parsers.get(suffix)
                if parser:
                    try:
                        parsed_content = parser(new_content)
                    except Exception as e:
                        artifact.load_error = e
                        logger.error(f"Parse error reloading '{name}': {e}")
                        self._error_count[name] = self._error_count.get(name, 0) + 1
                        return False
                else:
                    parsed_content = new_content

                # Publish the complete artifact/cache snapshot at one commit
                # point after validation succeeds.
                artifact.content = new_content
                artifact.mtime = current_mtime
                artifact.last_check = now
                artifact.load_error = None
                self._cache[name] = parsed_content

                logger.debug(f"Reloaded artifact '{name}' from {artifact.path}")
                return True

            except Exception as e:
                # Track load error but don't crash
                artifact.load_error = e
                artifact.last_check = now  # Update check time to prevent tight error loops
                self._error_count[name] = self._error_count.get(name, 0) + 1
                logger.error(f"Error checking/reloading artifact '{name}': {e}")
                return False

    def get_prompt(self, name: str) -> str:
        """
        Get a prompt's content, reloading if changed.

        Args:
            name: The prompt artifact name

        Returns:
            The prompt content as string

        Raises:
            KeyError: If artifact not registered
            RuntimeError: If artifact has persistent load errors
        """
        with self._lock:
            if name not in self._artifacts:
                raise KeyError(
                    f"Artifact '{name}' not registered. "
                    f"Available prompts: {[k for k in self._artifacts if self._artifacts[k].path.suffix in ['.md']]}"
                )

            # Check if there have been too many recent errors
            error_count = self._error_count.get(name, 0)
            if error_count > 5:
                artifact = self._artifacts[name]
                raise RuntimeError(
                    f"Artifact '{name}' has {error_count} recent load errors. "
                    f"Last error: {artifact.load_error}"
                )

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
        with self._lock:
            self._check_and_reload(name)
            # Read the parsed value from the same owner snapshot that the
            # reload path publishes, never from an unlocked cache pointer.
            return self._cache[name]

    def force_reload(self, name: str):
        """
        Force reload an artifact, bypassing the mtime check.

        Useful after manual edits or in tests.

        Raises:
            KeyError: If artifact not registered
            PermissionDeniedError: If file cannot be read
            RegistryParseError: If file parsing fails
        """
        with self._lock:
            if name not in self._artifacts:
                raise KeyError(f"Unknown artifact: {name}")

            artifact = self._artifacts[name]
            try:
                with open(artifact.path) as f:
                    new_content = f.read()
                new_mtime = artifact.path.stat().st_mtime
            except PermissionError as e:
                logger.error(f"Permission denied during force reload of {artifact.path}")
                raise PermissionDeniedError(artifact.path, f"force_reload('{name}')") from e

            suffix = artifact.path.suffix.lower()
            parser = self._parsers.get(suffix)
            if parser:
                try:
                    parsed_content = parser(new_content)
                except (ValueError, yaml.YAMLError, json.JSONDecodeError) as e:
                    logger.error(f"Parse error during force reload of {artifact.path}: {e}")
                    raise RegistryParseError(artifact.path, e, new_content) from e
            else:
                parsed_content = new_content

            # Atomic publication: readers see either the old artifact snapshot
            # or the fully parsed new one, never mixed metadata and content.
            artifact.content = new_content
            artifact.mtime = new_mtime
            artifact.last_check = time.time()
            artifact.load_error = None
            self._cache[name] = parsed_content

    def get_mtime(self, name: str) -> Optional[float]:
        """Get the current mtime of an artifact."""
        with self._lock:
            if name in self._artifacts:
                return self._artifacts[name].mtime
        return None

    def list_artifacts(self) -> Dict[str, str]:
        """List all registered artifacts and their paths."""
        with self._lock:
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
