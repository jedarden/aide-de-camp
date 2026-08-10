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

import json
import logging
import math
import queue
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


# Custom exception classes for clear error handling
class HotReloadError(Exception):
    """Base exception for hot-reload errors."""
    pass


class HotReloadTimeoutError(HotReloadError, TimeoutError):
    """Raised when a hot-reload operation exceeds its bounded time budget.

    File-system calls are made in a daemon worker so a blocked mount or mock
    cannot hold the caller forever.  The worker is deliberately not joined
    after the timeout: waiting for a stuck worker would defeat fail-fast
    behavior.
    """

    def __init__(self, path: Path, operation: str, timeout: float, reason: str):
        self.path = path
        self.operation = operation
        self.timeout = timeout
        self.reason = reason
        super().__init__(
            f"Hot-reload operation timed out: operation='{operation}', "
            f"path='{path}', timeout={timeout:.3f}s. Reason: {reason}. "
            "Action: check whether the file or filesystem is blocked, verify "
            "mount/storage health and permissions, then retry the operation."
        )


class PermissionDeniedError(HotReloadError):
    """Raised when file permission is denied."""

    def __init__(self, path: Path, operation: str, reason: str = "the file is not readable"):
        self.path = path
        self.operation = operation
        self.reason = reason
        super().__init__(
            f"Hot-reload operation '{operation}' failed for path '{path}'. "
            f"Reason: permission denied ({reason}). Action: check file "
            f"permissions with 'ls -la {path.parent}' and ensure the current "
            "user has read access before retrying."
        )


class RegistryNotFoundError(HotReloadError):
    """Raised when registry file is not found."""

    def __init__(self, path: Path, operation: str = "access file"):
        self.path = path
        self.operation = operation
        self.reason = "the path does not exist"
        super().__init__(
            f"Hot-reload operation '{operation}' failed for path '{path}'. "
            "Reason: the path does not exist. Action: verify the file exists "
            "at the expected location and check the configured path before "
            "retrying."
        )


class RegistryParseError(HotReloadError):
    """Raised when registry file parsing fails."""

    def __init__(
        self,
        path: Path,
        parse_error: Exception,
        content_preview: str = "",
        operation: str = "parse configuration",
    ):
        self.path = path
        self.parse_error = parse_error
        self.operation = operation
        self.reason = str(parse_error)
        self.content_preview = content_preview[:200] if content_preview else ""

        # Extract line/column info if available
        details = str(parse_error)
        error_details = f"Parse error: {details}"

        super().__init__(
            f"Hot-reload operation '{operation}' failed for path '{path}'. "
            f"Reason: {error_details}. Action: validate the YAML/JSON syntax "
            "and correct the reported line/column before retrying. "
            f"{f'Content preview: {self.content_preview}...' if self.content_preview else ''}"
        )


class EmptyRegistryError(HotReloadError):
    """Raised when registry file is empty or contains no data."""

    def __init__(
        self,
        path: Path,
        operation: str = "load configuration",
        reason: str = "the file is empty",
    ):
        self.path = path
        self.operation = operation
        self.reason = reason
        super().__init__(
            f"Hot-reload operation '{operation}' failed for path '{path}'. "
            f"Reason: {reason}. Action: provide non-empty, valid YAML or JSON "
            "configuration and retry the operation."
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
    MAX_RETRIES = 3  # Retries after the initial attempt (four attempts total)
    RETRY_DELAY = 0.1  # Initial exponential-backoff delay in seconds
    # Keep this strictly below the five-second acceptance limit.  The value is
    # also the complete budget for a public operation, including retries,
    # parsing, and lock acquisition.
    FILE_OPERATION_TIMEOUT = 4.0

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

    def _operation_deadline(self) -> float:
        """Return a monotonic deadline for one hot-reload operation."""
        try:
            configured = float(self.FILE_OPERATION_TIMEOUT)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Hot-reload operation configuration failed for path '<manager>'. "
                f"Reason: FILE_OPERATION_TIMEOUT={self.FILE_OPERATION_TIMEOUT!r} "
                "is not numeric. Action: configure a positive timeout below "
                "5 seconds."
            ) from exc
        if not math.isfinite(configured) or configured <= 0:
            raise ValueError(
                "Hot-reload operation configuration failed for path '<manager>'. "
                f"Reason: FILE_OPERATION_TIMEOUT={configured} is not positive. "
                "Action: configure a positive timeout below 5 seconds."
            )
        return time.monotonic() + min(configured, 4.0)

    @staticmethod
    def _remaining(deadline: float) -> float:
        """Return remaining operation budget in seconds."""
        return deadline - time.monotonic()

    def _run_with_timeout(
        self,
        path: Path,
        operation: str,
        callback: Callable[[], Any],
        deadline: float,
    ) -> Any:
        """Run one potentially blocking callback without waiting forever.

        ``open``/``read``/``stat`` are synchronous APIs and cannot be
        cancelled safely once entered.  A daemon worker lets the caller stop
        waiting at the operation deadline while ensuring a stuck worker cannot
        keep the test process alive during interpreter shutdown.
        """
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise HotReloadTimeoutError(
                path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "the operation budget was exhausted before the callback started",
            )

        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                result_queue.put((True, callback()))
            except BaseException as exc:  # transfer callback failures to caller
                result_queue.put((False, exc))

        worker = threading.Thread(
            target=run,
            name=f"hot-reload-{operation[:32]}",
            daemon=True,
        )
        worker.start()
        worker.join(timeout=remaining)

        if worker.is_alive():
            timeout = min(float(self.FILE_OPERATION_TIMEOUT), 4.0)
            raise HotReloadTimeoutError(
                path,
                operation,
                timeout,
                f"the callback did not finish within the {timeout:.3f}s deadline",
            )

        succeeded, value = result_queue.get_nowait()
        if succeeded:
            return value
        raise value

    @contextmanager
    def _locked(self, operation: str, path: Path, deadline: float):
        """Acquire the manager lock with the same bounded operation budget."""
        remaining = self._remaining(deadline)
        if remaining <= 0 or not self._lock.acquire(timeout=max(remaining, 0)):
            raise HotReloadTimeoutError(
                path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "waiting for another hot-reload operation to release the manager lock",
            )
        try:
            yield
        finally:
            self._lock.release()

    @staticmethod
    def _validate_name(name: str, operation: str, path: str) -> None:
        """Reject invalid artifact names before mutating manager state."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Hot-reload operation '{operation}' failed for path '{path}'. "
                "Reason: artifact name must be a non-empty string. Action: "
                "provide a stable artifact name such as 'router' and retry."
            )

    def _validate_file(self, path: Path, operation: str, deadline: float) -> float:
        """Validate that ``path`` is a regular file and return its mtime."""
        try:
            file_stat = self._run_with_timeout(
                path,
                f"{operation}: validate path",
                path.stat,
                deadline,
            )
        except HotReloadTimeoutError:
            raise
        except FileNotFoundError as exc:
            raise RegistryNotFoundError(path, operation) from exc
        except PermissionError as exc:
            raise PermissionDeniedError(path, operation, str(exc)) from exc
        except OSError as exc:
            raise OSError(
                f"Hot-reload operation '{operation}' failed for path '{path}'. "
                f"Reason: {type(exc).__name__}: {exc}. Action: check the path, "
                "filesystem, and permissions, then retry."
            ) from exc

        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(
                f"Hot-reload operation '{operation}' failed for path '{path}'. "
                "Reason: the path is not a regular file. Action: point the "
                "artifact at a readable file instead of a directory or device."
            )
        return file_stat.st_mtime

    def _sleep_before_retry(
        self,
        path: Path,
        operation: str,
        delay: float,
        deadline: float,
    ) -> None:
        """Sleep only inside the remaining retry budget."""
        remaining = self._remaining(deadline)
        if remaining <= 0:
            raise HotReloadTimeoutError(
                path,
                operation,
                min(float(self.FILE_OPERATION_TIMEOUT), 4.0),
                "retry backoff exhausted the operation budget",
            )
        self._run_with_timeout(
            path,
            f"{operation}: retry backoff",
            lambda: time.sleep(min(delay, remaining)),
            deadline,
        )

    def _read_file_with_retry(
        self,
        path: Path,
        operation: str = "read",
        deadline: Optional[float] = None,
    ) -> str:
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
        deadline = self._operation_deadline() if deadline is None else deadline
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                content = self._run_with_timeout(
                    path,
                    operation,
                    lambda: self._read_once(path),
                    deadline,
                )
                # Check for empty files
                if not content.strip() and path.suffix.lower() in ['.yaml', '.yml', '.json']:
                    logger.warning(f"Empty registry file detected: {path}")
                return content
            except HotReloadTimeoutError:
                raise
            except PermissionError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient permission error during {operation} "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    # Raise custom permission error with actionable guidance
                    logger.error(
                        f"Permission denied after {self.MAX_RETRIES} retries for {path}"
                    )
                    raise PermissionDeniedError(path, operation, str(e)) from e
            except FileNotFoundError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient not found error during {operation} "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    # Raise custom not found error with actionable guidance
                    logger.error(f"File not found after {self.MAX_RETRIES} retries for {path}")
                    raise RegistryNotFoundError(path, operation) from e
            except OSError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient OS error during {operation} "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    # Final attempt failed - enhance error message
                    error_type = type(e).__name__
                    enhanced_msg = (
                        f"Hot-reload operation '{operation}' failed for path '{path}'. "
                        f"Reason: {error_type}: {e}. Action: check the file, "
                        "filesystem, and permissions, then retry."
                    )
                    logger.error(f"Failed after {self.MAX_RETRIES} retries: {enhanced_msg}")
                    raise type(e)(enhanced_msg) from e

        # Should never reach here, but handle gracefully
        if last_error:
            raise last_error
        raise RuntimeError(f"Unexpected error in _read_file_with_retry for {path}")

    @staticmethod
    def _read_once(path: Path) -> str:
        """Read and close one file; executed inside a timeout worker."""
        with open(path, "r") as file_handle:
            return file_handle.read()

    def _get_mtime_with_retry(
        self,
        path: Path,
        operation: str = "get file modification time",
        deadline: Optional[float] = None,
    ) -> float:
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
        deadline = self._operation_deadline() if deadline is None else deadline
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return self._run_with_timeout(path, operation, path.stat, deadline).st_mtime
            except HotReloadTimeoutError:
                raise
            except PermissionError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient permission error getting mtime "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    logger.error(f"Permission denied getting mtime for {path}")
                    raise PermissionDeniedError(path, operation, str(e)) from e
            except FileNotFoundError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient not found error getting mtime "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    logger.error(f"File not found getting mtime for {path}")
                    raise RegistryNotFoundError(path, operation) from e
            except OSError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"Transient OS error getting mtime "
                        f"(retry {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    self._sleep_before_retry(
                        path, operation, self.RETRY_DELAY * (2 ** attempt), deadline
                    )
                else:
                    raise OSError(
                        f"Hot-reload operation '{operation}' failed for path '{path}'. "
                        f"Reason: {type(e).__name__}: {e}. Action: check the "
                        "filesystem and permissions, then retry."
                    ) from e

        # Should never reach here
        if last_error:
            raise last_error
        raise RuntimeError(f"Unexpected error in _get_mtime_with_retry for {path}")

    def register_prompt(
        self,
        name: str,
        path: str,
        _deadline: Optional[float] = None,
    ):
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
        operation = f"register_prompt('{name}')"
        self._validate_name(name, operation, str(path))
        full_path = Path(path).expanduser().absolute()
        deadline = self._operation_deadline() if _deadline is None else _deadline
        with self._locked(operation, full_path, deadline):
            try:
                mtime = self._validate_file(full_path, operation, deadline)

                # Read content with retry
                content = self._read_file_with_retry(full_path, operation, deadline)

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

    def register_config(
        self,
        name: str,
        path: str,
        _deadline: Optional[float] = None,
    ):
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
        operation = f"register_config('{name}')"
        self._validate_name(name, operation, str(path))
        full_path = Path(path).expanduser().absolute()
        deadline = self._operation_deadline() if _deadline is None else _deadline
        with self._locked(operation, full_path, deadline):
            try:
                mtime = self._validate_file(full_path, operation, deadline)

                # Read content with retry
                content = self._read_file_with_retry(full_path, operation, deadline)

                # Check for empty files before parsing
                if not content.strip():
                    logger.error(f"Empty config file detected: {full_path}")
                    raise EmptyRegistryError(full_path, operation)

                # Parse based on extension
                suffix = full_path.suffix.lower()
                parser = self._parsers.get(suffix)
                if parser is None:
                    logger.error(f"Unsupported file type: {suffix}")
                    raise ValueError(
                        f"Hot-reload operation '{operation}' failed for path '{full_path}'. "
                        f"Reason: unsupported file type '{suffix}'. Action: use one "
                        f"of the supported extensions {list(self._parsers.keys())}."
                    )

                parsed = self._parse_with_timeout(
                    full_path, operation, parser, content, deadline
                )
                if parsed is None:
                    raise EmptyRegistryError(
                        full_path,
                        operation,
                        "the parser returned no configuration data",
                    )

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

    def _parse_with_timeout(
        self,
        path: Path,
        operation: str,
        parser: Callable[[str], Any],
        content: str,
        deadline: float,
    ) -> Any:
        """Parse content under the same deadline as its file operation."""
        try:
            return self._run_with_timeout(
                path,
                f"{operation}: parse content",
                lambda: parser(content),
                deadline,
            )
        except HotReloadTimeoutError:
            raise
        except Exception as exc:
            raise RegistryParseError(path, exc, content, operation) from exc

    def _check_and_reload(
        self,
        name: str,
        deadline: Optional[float] = None,
    ) -> bool:
        """
        Check if an artifact needs reloading and reload if so, with thread safety.

        Returns:
            True if reloaded successfully, False otherwise (even on error)
        """
        operation = f"check_and_reload('{name}')"
        deadline = self._operation_deadline() if deadline is None else deadline
        artifact = self._artifacts.get(name)
        artifact_path = artifact.path if artifact else Path("<unregistered-artifact>")
        with self._locked(operation, artifact_path, deadline):
            if name not in self._artifacts:
                raise KeyError(
                    f"Hot-reload operation '{operation}' failed for path "
                    "'<unregistered-artifact>'. Reason: artifact is not registered. "
                    "Action: register the file before requesting a reload."
                )

            artifact = self._artifacts[name]
            now = time.time()

            # Throttle checks
            if now - artifact.last_check < self.CHECK_INTERVAL:
                return False

            try:
                # Check mtime with retry
                current_mtime = self._get_mtime_with_retry(
                    artifact.path, operation, deadline
                )

                if current_mtime <= artifact.mtime:
                    artifact.last_check = now
                    return False

                # Reload with retry
                new_content = self._read_file_with_retry(
                    artifact.path,
                    operation,
                    deadline,
                )

                # Parse completely before publishing artifact metadata. A
                # malformed replacement keeps the old content/mtime/cache.
                suffix = artifact.path.suffix.lower()
                parser = self._parsers.get(suffix)
                if parser:
                    try:
                        parsed_content = self._parse_with_timeout(
                            artifact.path, operation, parser, new_content, deadline
                        )
                    except HotReloadTimeoutError:
                        raise
                    except RegistryParseError as e:
                        artifact.load_error = e
                        logger.error(f"Reload parse failed for '{name}': {e}")
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

            except HotReloadTimeoutError as e:
                artifact.load_error = e
                artifact.last_check = now
                self._error_count[name] = self._error_count.get(name, 0) + 1
                logger.error(f"Fail-fast timeout reloading '{name}': {e}")
                raise
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
        operation = f"get_prompt('{name}')"
        deadline = self._operation_deadline()
        artifact = self._artifacts.get(name)
        artifact_path = artifact.path if artifact else Path("<unregistered-artifact>")
        with self._locked(operation, artifact_path, deadline):
            if name not in self._artifacts:
                raise KeyError(
                    f"Hot-reload operation '{operation}' failed for path "
                    f"'<unregistered-artifact>'. Reason: artifact '{name}' is "
                    "not registered. Action: register the prompt file before "
                    "requesting it. Available prompts: "
                    f"{[k for k in self._artifacts if self._artifacts[k].path.suffix in ['.md']]}"
                )

            # Check if there have been too many recent errors
            error_count = self._error_count.get(name, 0)
            if error_count > 5:
                artifact = self._artifacts[name]
                raise RuntimeError(
                    f"Hot-reload operation '{operation}' failed for path "
                    f"'{artifact.path}'. Reason: artifact has {error_count} "
                    f"recent load errors; last error: {artifact.load_error}. "
                    "Action: fix the file or filesystem error shown above and "
                    "retry the prompt load."
                )

            self._check_and_reload(name, deadline)
            return self._cache[name]

    def get_config(self, name: str) -> Any:
        """
        Get a config's parsed content, reloading if changed.

        Args:
            name: The config artifact name

        Returns:
            The parsed config (dict for YAML)
        """
        operation = f"get_config('{name}')"
        deadline = self._operation_deadline()
        artifact = self._artifacts.get(name)
        artifact_path = artifact.path if artifact else Path("<unregistered-artifact>")
        with self._locked(operation, artifact_path, deadline):
            if name not in self._artifacts:
                raise KeyError(
                    f"Hot-reload operation '{operation}' failed for path "
                    "'<unregistered-artifact>'. Reason: artifact is not registered. "
                    "Action: register the configuration file before requesting it."
                )
            self._check_and_reload(name, deadline)
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
        operation = f"force_reload('{name}')"
        deadline = self._operation_deadline()
        artifact = self._artifacts.get(name)
        artifact_path = artifact.path if artifact else Path("<unregistered-artifact>")
        with self._locked(operation, artifact_path, deadline):
            if name not in self._artifacts:
                raise KeyError(
                    f"Hot-reload operation '{operation}' failed for path "
                    "'<unregistered-artifact>'. Reason: artifact is not registered. "
                    "Action: register the file before forcing a reload."
                )

            artifact = self._artifacts[name]
            # Atomic writers may briefly replace a file.  Retry the complete
            # read/stat sequence without publishing partial state.
            new_content = self._read_file_with_retry(
                artifact.path, operation, deadline
            )
            new_mtime = self._get_mtime_with_retry(
                artifact.path, operation, deadline
            )

            suffix = artifact.path.suffix.lower()
            parser = self._parsers.get(suffix)
            if parser:
                parsed_content = self._parse_with_timeout(
                    artifact.path, operation, parser, new_content, deadline
                )
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
        operation = f"get_mtime('{name}')"
        deadline = self._operation_deadline()
        artifact = self._artifacts.get(name)
        artifact_path = artifact.path if artifact else Path("<unregistered-artifact>")
        with self._locked(operation, artifact_path, deadline):
            if name in self._artifacts:
                return self._artifacts[name].mtime
        return None

    def list_artifacts(self) -> Dict[str, str]:
        """List all registered artifacts and their paths."""
        operation = "list_artifacts()"
        deadline = self._operation_deadline()
        with self._locked(operation, Path("<artifact-registry>"), deadline):
            return {
                name: str(artifact.path)
                for name, artifact in self._artifacts.items()
            }


# Singleton instance for the application
_reload_manager: Optional[HotReloadManager] = None
_reload_manager_lock = threading.Lock()


def get_reload_manager() -> HotReloadManager:
    """Get or create the hot-reload manager singleton.

    Initialization is serialized because application startup, test fixtures,
    and worker threads can request the singleton concurrently.  The manager's
    own RLock protects artifact reads after construction.
    """
    global _reload_manager
    operation = "get_reload_manager()"
    timeout = min(float(HotReloadManager.FILE_OPERATION_TIMEOUT), 4.0)
    deadline = time.monotonic() + timeout
    if not _reload_manager_lock.acquire(timeout=timeout):
        raise HotReloadTimeoutError(
            Path("<reload-manager>"),
            operation,
            timeout,
            "waiting for another thread to finish singleton initialization",
        )
    try:
        if _reload_manager is None:
            manager = HotReloadManager()
            manager.register_prompt('router', 'prompts/router.md', _deadline=deadline)
            manager.register_prompt('synthesize', 'prompts/synthesize.md', _deadline=deadline)
            manager.register_prompt('voice', 'prompts/voice.md', _deadline=deadline)
            manager.register_prompt('urgency', 'prompts/urgency.md', _deadline=deadline)
            manager.register_prompt('fetch_status', 'prompts/fetch/status.md', _deadline=deadline)
            manager.register_prompt('fetch_action', 'prompts/fetch/action.md', _deadline=deadline)
            manager.register_config('registry', 'config/registry.yaml', _deadline=deadline)
            manager.register_config('monitoring', 'config/monitoring.yaml', _deadline=deadline)
            manager.register_config('exceptions', 'config/exceptions.yaml', _deadline=deadline)
            # Publish only after every built-in artifact is registered.  A
            # failed initialization cannot expose a half-populated manager.
            _reload_manager = manager
        return _reload_manager
    finally:
        _reload_manager_lock.release()
