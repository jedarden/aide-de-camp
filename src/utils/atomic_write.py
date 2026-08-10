"""
Atomic write utilities for filesystem operations.

This module provides safe write operations that prevent data corruption
by using temporary files and atomic renames, with comprehensive error
handling, rollback support, and logging.
"""

import logging
import os
import random
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)

_write_locks: dict[str, threading.RLock] = {}
_write_locks_guard = threading.Lock()


def _path_lock(path: Union[str, Path], locks: dict[str, threading.RLock], guard: threading.Lock) -> threading.RLock:
    """Return the process-local lock for one filesystem path."""
    key = str(Path(path).absolute())
    with guard:
        return locks.setdefault(key, threading.RLock())


def _write_all(fd: int, data: bytes) -> None:
    """Write all bytes, handling a valid short ``os.write`` result."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write while publishing atomic file content")
        view = view[written:]


class AtomicWriteError(Exception):
    """Base exception for atomic write errors."""
    pass


class AtomicWriteRollbackError(AtomicWriteError):
    """Raised when rollback fails after a write error."""
    pass


def _cleanup_temp_path(
    path: Path,
    operation_id: str,
    reason: str,
    *,
    strict: bool = False,
) -> bool:
    """Remove a staging path without turning an idempotent race into a failure.

    Cleanup runs after the publish/error decision has been made, so it must be
    safe when another cleanup owner removed the path first.  A permission or
    filesystem error is still recorded with the path and operation context.
    Callers performing rollback can request ``strict`` handling to surface an
    incomplete rollback as :class:`AtomicWriteRollbackError`; best-effort
    cleanup callers leave the original operation result unchanged.
    """
    try:
        path.unlink(missing_ok=True)
    except FileNotFoundError:
        # ``missing_ok`` handles the normal case; this branch also covers a
        # mocked or platform-specific unlink implementation and is idempotent.
        logger.debug(
            "[%s] Temp cleanup already complete for %s (%s)",
            operation_id,
            path,
            reason,
        )
        return True
    except PermissionError as error:
        message = (
            f"[{operation_id}] Permission denied cleaning up temp file {path} "
            f"after {reason}: {error}"
        )
        logger.error(message)
        if strict:
            raise AtomicWriteRollbackError(
                f"Permission denied rolling back temp file {path}: {error}. "
                "The temporary file may persist; correct its permissions and retry."
            ) from error
        return False
    except OSError as error:
        message = (
            f"[{operation_id}] Failed to clean up temp file {path} after "
            f"{reason}: {type(error).__name__}: {error}"
        )
        logger.error(message)
        if strict:
            raise AtomicWriteRollbackError(
                f"Failed to rollback temp file {path}: {error}. "
                "The temporary file may persist; retry cleanup when the resource is available."
            ) from error
        return False

    logger.debug("[%s] Cleaned up temp file %s (%s)", operation_id, path, reason)
    return True


def _atomic_backup(source: Path, destination: Path, operation_id: str) -> None:
    """Copy ``source`` to ``destination`` without exposing a partial backup."""
    temp_fd, temp_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f'.{destination.name}.tmp_{operation_id}_',
        suffix='.bak',
    )
    temp_path_obj = Path(temp_path)
    try:
        os.close(temp_fd)
        temp_fd = None
        shutil.copy2(source, temp_path_obj)
        os.replace(temp_path_obj, destination)
    except BaseException:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError as close_error:
                logger.warning(
                    "[%s] Failed to close backup temp descriptor for %s: %s",
                    operation_id,
                    temp_path_obj,
                    close_error,
                )
        _cleanup_temp_path(temp_path_obj, operation_id, "atomic backup error")
        raise


def _atomic_write_with_retries(
    filepath: Union[str, Path],
    content: Union[str, bytes],
    mode: str = 'w',
    *,
    create_backup: bool = False,
    validate_fn: Optional[Callable[[Union[str, bytes]], bool]] = None,
    cleanup_verify: bool = True,
    max_retries: int = 0,
    initial_delay: float = 0.1
) -> Optional[Path]:
    """
    Write content to a file atomically with comprehensive error handling.

    This function writes to a temporary file in the same directory as the target,
    then uses os.replace() for atomic overwrite. On all platforms, os.replace()
    is atomic when both files are on the same filesystem, ensuring readers either
    see the old content or the complete new content, never a partial write.

    Args:
        filepath: Target file path (str or Path object)
        content: Content to write (str for text mode, bytes for binary mode)
        mode: Write mode - 'w' for text, 'wb' for binary (default: 'w')
        create_backup: If True, creates .bak backup of original file before overwrite
        validate_fn: Optional validation function called with content before write.
                     Should return True if content is valid, False otherwise.
                     If validation fails, no write occurs and original file is preserved.
        cleanup_verify: If True, verifies no temp files remain after operation
        max_retries: Maximum number of retry attempts for transient failures (default: 0, no retries)
        initial_delay: Initial delay in seconds between retries (default: 0.1)

    Returns:
        Path to backup file if create_backup=True and original file existed,
        None otherwise

    Raises:
        PermissionError: If lacking write permissions for the directory
        OSError: If disk is full or other filesystem error occurs
        TypeError: If content type doesn't match mode (e.g., str with 'wb')
        ValueError: If validation function returns False

    Example:
        >>> atomic_write('/path/to/config.json', '{"key": "value"}')
        >>> # File is guaranteed to be complete or unchanged

        >>> # With validation
        >>> def is_valid_json(content):
        ...     try:
        ...         json.loads(content)
        ...         return True
        ...     except json.JSONDecodeError:
        ...         return False
        >>> atomic_write('/path/to/config.json', content, validate_fn=is_valid_json)

    Note:
        - Requires write permission to the containing directory
        - Preserves file permissions on overwrite (replace retains metadata)
        - Temp files are cleaned up on all error paths
        - All operations are logged at INFO level on success, WARNING on failure
    """
    filepath = Path(filepath)
    operation_id = str(uuid.uuid4())[:8]
    backup_path: Optional[Path] = None

    logger.info(
        f"[{operation_id}] Starting atomic write to {filepath}",
        extra={"filepath": str(filepath), "operation_id": operation_id}
    )

    # Retry logic for transient failures
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # Core atomic write operation (wrapped in retry loop)
            return _atomic_write_impl(
                filepath, content, mode, operation_id,
                create_backup, validate_fn, cleanup_verify, backup_path
            )

        except (OSError, PermissionError) as e:
            last_exception = e
            if attempt < max_retries:
                # Log retry attempt with attempt number and error type
                logger.info(
                    f"[{operation_id}] Retry attempt {attempt + 1}/{max_retries} for atomic write: "
                    f"{type(e).__name__}: {e}"
                )
                # Add jitter to prevent thundering herd problem
                jittered_delay = delay * (0.5 + random.random() * 0.5)
                time.sleep(jittered_delay)
                delay *= 2.0  # Exponential backoff: 100ms, 200ms, 400ms
            else:
                # All retries exhausted - log final failure
                logger.error(
                    f"[{operation_id}] All {max_retries} retry attempts exhausted for atomic write: "
                    f"{type(e).__name__}: {e}"
                )
                raise

    # Should never reach here, but handle gracefully
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Unexpected error in atomic write for {filepath}")


def atomic_write(
    filepath: Union[str, Path],
    content: Union[str, bytes],
    mode: str = 'w',
    *,
    create_backup: bool = False,
    validate_fn: Optional[Callable[[Union[str, bytes]], bool]] = None,
    cleanup_verify: bool = True,
    max_retries: int = 0,
    initial_delay: float = 0.1,
) -> Optional[Path]:
    """Serialize same-path writers, then publish with P1 temp-file replace.

    ``os.replace`` prevents partial readers, while this owner lock prevents a
    slower writer from replacing a newer complete file after both writers have
    read the same old generation.
    """
    lock = _path_lock(filepath, _write_locks, _write_locks_guard)
    with lock:
        return _atomic_write_with_retries(
            filepath,
            content,
            mode,
            create_backup=create_backup,
            validate_fn=validate_fn,
            cleanup_verify=cleanup_verify,
            max_retries=max_retries,
            initial_delay=initial_delay,
        )


def _atomic_write_impl(
    filepath: Path,
    content: Union[str, bytes],
    mode: str,
    operation_id: str,
    create_backup: bool,
    validate_fn: Optional[Callable[[Union[str, bytes]], bool]],
    cleanup_verify: bool,
    backup_path: Optional[Path]
) -> Optional[Path]:
    """
    Core implementation of atomic write operation.

    This function performs the actual atomic write without retry logic.
    Retry logic is handled by the atomic_write wrapper function.
    """
    try:
        # Validate content type matches mode
        if mode == 'wb':
            if not isinstance(content, bytes):
                error_msg = f"Binary mode requires bytes content, got {type(content).__name__}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise TypeError(error_msg)
        elif mode == 'w':
            if not isinstance(content, str):
                error_msg = f"Text mode requires str content, got {type(content).__name__}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise TypeError(error_msg)
        else:
            error_msg = f"Invalid mode '{mode}'. Must be 'w' or 'wb'"
            logger.error(f"[{operation_id}] {error_msg}")
            raise ValueError(error_msg)

        # Run validation if provided
        if validate_fn is not None:
            logger.debug(f"[{operation_id}] Running validation function")
            if not validate_fn(content):
                error_msg = f"Validation failed for content in {filepath}"
                logger.warning(f"[{operation_id}] {error_msg}")
                raise ValueError(error_msg)

        # Create parent directories
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"[{operation_id}] Parent directories created/verified")
        except OSError as e:
            error_msg = f"Cannot create parent directories for {filepath.parent}: {e}"
            logger.error(f"[{operation_id}] {error_msg}")
            raise PermissionError(error_msg) from e

        # Create backup of original file if requested and file exists
        original_existed = filepath.exists()
        if create_backup and original_existed:
            backup_path = filepath.with_suffix(filepath.suffix + '.bak')
            try:
                _atomic_backup(filepath, backup_path, operation_id)
                logger.info(f"[{operation_id}] Created backup at {backup_path}")
            except OSError as e:
                error_msg = f"Failed to create backup at {backup_path}: {e}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise OSError(error_msg) from e

        # Create temporary file in same directory as target (ensures same filesystem)
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=filepath.parent,
                prefix=f'.{filepath.name}.tmp_{operation_id}_',
                suffix='.tmp'
            )
            logger.debug(f"[{operation_id}] Created temp file {temp_path}")
        except OSError as e:
            error_msg = f"Cannot create temp file in {filepath.parent}: {e}"
            logger.error(f"[{operation_id}] {error_msg}")
            raise PermissionError(error_msg) from e

        temp_path_obj = Path(temp_path)

        try:
            # Write content to temp file
            try:
                if mode == 'wb':
                    _write_all(fd, content)
                else:
                    # Text mode: encode to UTF-8
                    _write_all(fd, content.encode('utf-8'))
                logger.debug(f"[{operation_id}] Content written to temp file")
            except OSError as e:
                error_msg = f"Failed to write to temp file {temp_path}: {e}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise

            # Sync to disk - important for crash safety
            try:
                os.fsync(fd)
                logger.debug(f"[{operation_id}] Temp file synced to disk")
            except OSError as e:
                logger.warning(f"[{operation_id}] fsync failed (non-critical): {e}")
                # Continue anyway - fsync failure is not critical on all systems

            os.close(fd)
            fd = None  # Mark as closed

            # Verify temp file content (catch disk full errors early)
            if not temp_path_obj.exists():
                error_msg = f"Temp file {temp_path} does not exist after write"
                logger.error(f"[{operation_id}] {error_msg}")
                raise OSError(error_msg)

            # Check temp file size
            try:
                temp_size = temp_path_obj.stat().st_size
                expected_size = len(content) if isinstance(content, bytes) else len(content.encode('utf-8'))
                if temp_size != expected_size:
                    error_msg = f"Temp file size mismatch: expected {expected_size}, got {temp_size}"
                    logger.error(f"[{operation_id}] {error_msg}")
                    raise OSError(error_msg)
                logger.debug(f"[{operation_id}] Temp file size verified: {temp_size} bytes")
            except OSError as e:
                error_msg = f"Failed to verify temp file size: {e}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise

            # Atomic replace - replaces target if it exists
            try:
                os.replace(temp_path, filepath)
                try:
                    directory_fd = os.open(filepath.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        try:
                            os.close(directory_fd)
                        except OSError as close_error:
                            # Closing the directory descriptor is cleanup, not
                            # the publication commit point.  Do not mask a
                            # successful replace (or an earlier fsync error).
                            logger.warning(
                                f"[{operation_id}] directory descriptor cleanup failed "
                                f"for {filepath.parent}: {close_error}"
                            )
                except OSError as sync_error:
                    logger.warning(f"[{operation_id}] directory fsync failed (non-critical): {sync_error}")
                logger.info(
                    f"[{operation_id}] Atomic replace successful: {temp_path} -> {filepath}",
                    extra={"backup_created": backup_path is not None}
                )
            except OSError as e:
                error_msg = f"Failed atomic replace {temp_path} -> {filepath}: {e}"
                logger.error(f"[{operation_id}] {error_msg}")
                raise

            # Verify no orphaned temp files
            if cleanup_verify:
                orphaned_files = _verify_no_orphaned_temps(filepath.parent, operation_id)
                if orphaned_files:
                    logger.warning(
                        f"[{operation_id}] Found orphaned temp files from atomic write operation: {orphaned_files}"
                    )
                    # Clean them up with idempotent, best-effort handling.  A
                    # concurrent startup cleanup may have claimed one already.
                    for orphan in orphaned_files:
                        _cleanup_temp_path(
                            orphan,
                            operation_id,
                            "orphaned temp-file cleanup",
                        )

            logger.info(
                f"[{operation_id}] Atomic write completed successfully",
                extra={
                    "filepath": str(filepath),
                    "backup_path": str(backup_path) if backup_path else None,
                    "operation_id": operation_id
                }
            )
            return backup_path

        except BaseException:
            # Clean up temp file on any error with enhanced atomic write failure handling
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as close_error:
                    logger.warning(
                        f"[{operation_id}] Failed to close temp file descriptor "
                        f"after atomic write error: {close_error}"
                    )
            # Do not use an ``exists()`` check before unlinking: another
            # cleanup owner can remove the file between those two operations.
            # Best-effort cleanup must never replace the original write error.
            _cleanup_temp_path(
                temp_path_obj,
                operation_id,
                "atomic write error",
            )
            raise

    except Exception as e:
        logger.error(
            f"[{operation_id}] Atomic write failed with exception: {type(e).__name__}: {e}",
            exc_info=True,
            extra={"filepath": str(filepath), "operation_id": operation_id}
        )
        raise


@contextmanager
def atomic_write_rollback(filepath: Union[str, Path], mode: str = 'w'):
    """Serialize one rollback transaction per target path.

    The lock spans the caller's context block and the final ``os.replace`` so
    two read/modify/write users cannot publish stale snapshots out of order.
    """
    filepath = Path(filepath)
    lock = _path_lock(filepath, _write_locks, _write_locks_guard)
    with lock:
        with _atomic_write_rollback_locked(filepath, mode) as temp_path:
            yield temp_path


@contextmanager
def _atomic_write_rollback_locked(filepath: Union[str, Path], mode: str = 'w'):
    """
    Context manager for atomic write with automatic rollback on error.

    Creates a temporary file that you can write to within the context.
    If the context block completes successfully, the temp file is atomically
    moved to the target filepath. If an exception occurs, the temp file is
    cleaned up and the original file (if any) is preserved.

    Args:
        filepath: Target file path (str or Path object)
        mode: Write mode - 'w' for text, 'wb' for binary (default: 'w')

    Yields:
        Path object for the temporary file to write to

    Raises:
        PermissionError: If lacking write permissions
        OSError: If disk is full or other filesystem error occurs
        AtomicWriteRollbackError: If rollback after failure fails

    Example:
        >>> with atomic_write_rollback('/path/to/config.json') as temp_path:
        ...     temp_path.write_text('{"key": "value"}')
        >>> # File is now atomically updated at target path

        >>> # With error handling and automatic cleanup
        >>> try:
        ...     with atomic_write_rollback('/path/to/data.txt') as temp:
        ...         temp.write_text(processed_data)
        ... except ValueError as e:
        ...     # Original file is preserved, temp file cleaned up automatically
        ...     pass

    Note:
        - If an exception occurs within the context block, the temp file is
          automatically cleaned up and the original file is unchanged
        - If rollback fails, AtomicWriteRollbackError is raised
        - All operations are logged
    """
    filepath = Path(filepath)
    operation_id = str(uuid.uuid4())[:8]

    logger.info(
        f"[{operation_id}] Starting atomic write rollback context for {filepath}",
        extra={"filepath": str(filepath), "operation_id": operation_id}
    )

    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Create temporary file.  Keep creation and descriptor cleanup separate so
    # a close failure cannot strand the staging file without a diagnostic.
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=filepath.parent,
            prefix=f'.{filepath.name}.tmp_{operation_id}_',
            suffix='.tmp'
        )
    except OSError as e:
        error_msg = f"Cannot create temp file in {filepath.parent}: {e}"
        logger.error(f"[{operation_id}] {error_msg}")
        raise PermissionError(error_msg) from e

    temp_path_obj = Path(temp_path)
    try:
        os.close(fd)  # Close it, caller will write to it
    except OSError as e:
        logger.error(
            f"[{operation_id}] Failed to close rollback temp descriptor for "
            f"{temp_path}: {e}"
        )
        _cleanup_temp_path(temp_path_obj, operation_id, "rollback temp descriptor cleanup")
        raise OSError(f"Failed to prepare rollback temp file {temp_path}: {e}") from e

    try:
        yield temp_path_obj

        # Context completed successfully, atomic replace
        if not temp_path_obj.exists():
            error_msg = f"Temp file {temp_path} does not exist after context block"
            logger.error(f"[{operation_id}] {error_msg}")
            raise OSError(error_msg)

        try:
            os.replace(temp_path, filepath)
            logger.info(
                f"[{operation_id}] Atomic replace successful (rollback context)",
                extra={"filepath": str(filepath)}
            )
        except OSError as e:
            error_msg = f"Failed atomic replace {temp_path} -> {filepath}: {e}"
            logger.error(f"[{operation_id}] {error_msg}")
            raise

    except BaseException as original_error:
        # Error in context block - rollback (cleanup temp file) with enhanced error handling
        logger.warning(
            f"[{operation_id}] Exception in context, rolling back atomic write operation",
            extra={"operation_id": operation_id}
        )

        # Strict mode reports a real rollback failure, while a concurrent
        # owner removing the temp file remains a successful/idempotent cleanup.
        try:
            _cleanup_temp_path(
                temp_path_obj,
                operation_id,
                "atomic write rollback",
                strict=True,
            )
        except AtomicWriteRollbackError as rollback_error:
            raise rollback_error from original_error

        raise


def _verify_no_orphaned_temps(directory: Path, operation_id: str) -> list[Path]:
    """
    Verify no orphaned temp files exist in directory.

    Returns list of orphaned temp files matching this operation's pattern.
    """
    try:
        pattern = f'.*tmp_{operation_id}_.*\\.tmp$'
        orphaned = list(directory.glob(pattern))
        return orphaned
    except Exception as e:
        logger.warning(f"Failed to verify orphaned temp files: {e}")
        return []


def cleanup_orphaned_temp_files(
    directory: Union[str, Path],
    pattern: str = '*.tmp',
    *,
    return_details: bool = False,
    raise_on_failure: bool = False
) -> Union[int, dict[str, Any]]:
    """
    Clean up orphaned temporary files in a directory with detailed error reporting.

    Useful for startup cleanup of any temp files that may have been left
    from previous crashes or interrupted operations.

    Args:
        directory: Directory to clean up
        pattern: Glob pattern for temp files (default: '*.tmp')
        return_details: If True, returns dict with detailed results (default: False for backward compatibility)
        raise_on_failure: If True, raises exception on cleanup failure (default: False)

    Returns:
        If return_details=False (default): Number of files successfully cleaned up (int)
        If return_details=True: Dictionary with detailed results:
        - 'cleaned': int - Number of files successfully cleaned up
        - 'failed': int - Number of files that failed to clean up
        - 'errors': list[str] - List of error messages for failed cleanups
        - 'directory': str - Directory that was cleaned

    Raises:
        OSError: If directory access fails and raise_on_failure=True
        PermissionError: If lacking permissions and raise_on_failure=True

    Example:
        >>> # Backward compatible - returns count
        >>> count = cleanup_orphaned_temp_files('/tmp', '*.tmp')
        >>> print(f"Cleaned up {count} orphaned temp files")

        >>> # Detailed results
        >>> result = cleanup_orphaned_temp_files('/tmp', '*.tmp', return_details=True)
        >>> print(f"Cleaned up {result['cleaned']} orphaned temp files")
        >>> if result['failed'] > 0:
        ...     print(f"Failed to clean up {result['failed']} files")
    """
    directory = Path(directory)
    result = {
        'cleaned': 0,
        'failed': 0,
        'errors': [],
        'directory': str(directory)
    }

    # Check if directory exists first
    try:
        if not directory.exists():
            logger.warning(f"Directory does not exist for cleanup: {directory}")
            if raise_on_failure:
                raise OSError(f"Directory does not exist: {directory}")
            return result if return_details else 0

        if not directory.is_dir():
            logger.error(f"Path is not a directory for cleanup: {directory}")
            if raise_on_failure:
                raise NotADirectoryError(f"Path is not a directory: {directory}")
            return result if return_details else 0

    except OSError as e:
        logger.error(f"Failed to access directory for cleanup {directory}: {e}")
        if raise_on_failure:
            raise
        result['errors'].append(f"Directory access failed: {e}")
        return result if return_details else 0

    # Clean up temp files
    try:
        temp_files = list(directory.glob(pattern))
        logger.debug(f"Found {len(temp_files)} temp files matching pattern '{pattern}' in {directory}")

        for temp_file in temp_files:
            try:
                # Use missing_ok=True for idempotent cleanup (safe if file already deleted)
                temp_file.unlink(missing_ok=True)
                result['cleaned'] += 1
                logger.debug(f"Cleaned up orphaned temp file: {temp_file}")

            except FileNotFoundError:
                # A concurrent cleanup owner won the race.  The requested
                # post-condition (the file is absent) already holds.
                logger.debug(f"Temp file already removed during cleanup: {temp_file}")

            except PermissionError as e:
                result['failed'] += 1
                error_msg = f"Permission denied cleaning up {temp_file}: {e}"
                result['errors'].append(error_msg)
                logger.warning(error_msg)

            except OSError as e:
                result['failed'] += 1
                error_msg = f"Failed to cleanup temp file {temp_file}: {e}"
                result['errors'].append(error_msg)
                logger.warning(error_msg)

    except PermissionError as e:
        error_msg = f"Permission denied listing temp files in {directory}: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        if raise_on_failure:
            raise PermissionError(error_msg) from e

    except OSError as e:
        error_msg = f"Failed to list temp files in {directory}: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        if raise_on_failure:
            raise OSError(error_msg) from e

    # Log summary
    if result['cleaned'] > 0 or result['failed'] > 0:
        logger.info(
            f"Cleanup complete for {directory}: {result['cleaned']} files removed, "
            f"{result['failed']} failed"
        )
    else:
        logger.debug(f"No temp files found for cleanup in {directory}")

    # Raise if requested and there were failures
    if raise_on_failure and result['failed'] > 0:
        raise OSError(
            f"Cleanup failed for {result['failed']} files in {directory}. "
            f"Errors: {'; '.join(result['errors'][:3])}"
        )

    return result if return_details else result['cleaned']


def atomic_append(
    filepath: Union[str, Path],
    content: Union[str, bytes],
    mode: str = 'a',
    *,
    validate_fn: Optional[Callable[[Union[str, bytes]], bool]] = None,
    max_retries: int = 0,
    initial_delay: float = 0.1,
) -> None:
    """Append one complete record under a per-path writer lock."""
    lock = _path_lock(filepath, _write_locks, _write_locks_guard)
    # The read/merge/replace sequence in the implementation is one logical
    # append transaction. Serializing it prevents two writers from losing one
    # another's records between the read and atomic replacement.
    with lock:
        return _atomic_append_impl(
            filepath,
            content,
            mode,
            validate_fn=validate_fn,
            max_retries=max_retries,
            initial_delay=initial_delay,
        )


def _atomic_append_impl(
    filepath: Union[str, Path],
    content: Union[str, bytes],
    mode: str = 'a',
    *,
    validate_fn: Optional[Callable[[Union[str, bytes]], bool]] = None,
    max_retries: int = 0,
    initial_delay: float = 0.1
) -> None:
    """
    Append content to a file atomically with error handling.

    This function implements atomic append for log files by writing to a
    temporary file and using atomic rename to append the content. This ensures
    that the append operation is atomic and won't result in partial writes.

    For small content (under PIPE_BUF size, typically 4KB), a single write()
    call is guaranteed to be atomic on POSIX systems. For larger content or
    when stronger guarantees are needed, this function uses temp file + rename.

    Args:
        filepath: Target file path (str or Path object)
        content: Content to append (str for text mode, bytes for binary mode)
        mode: Append mode - 'a' for text, 'ab' for binary (default: 'a')
        validate_fn: Optional validation function called with content before append.
                     Should return True if content is valid.
        max_retries: Maximum number of retry attempts for transient failures (default: 0)
        initial_delay: Initial delay in seconds between retries (default: 0.1)

    Raises:
        PermissionError: If lacking write permissions
        OSError: If filesystem error occurs
        ValueError: If validation function returns False

    Example:
        >>> atomic_append('/var/log/deletions.jsonl', '{"pod": "x", "status": "deleted"}\\n')
    """
    filepath = Path(filepath)
    operation_id = str(uuid.uuid4())[:8]

    logger.debug(
        f"[{operation_id}] Starting atomic append to {filepath}",
        extra={"filepath": str(filepath), "operation_id": operation_id}
    )

    # Validate content if validation function provided
    if validate_fn is not None:
        if not validate_fn(content):
            error_msg = f"Content validation failed for {filepath}"
            logger.error(f"[{operation_id}] {error_msg}")
            raise ValueError(error_msg)

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Retry logic for transient failures
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # For text mode, ensure content is string
            if mode == 'a' and isinstance(content, bytes):
                content = content.decode('utf-8')
            # For binary mode, ensure content is bytes
            elif mode == 'ab' and isinstance(content, str):
                content = content.encode('utf-8')

            # Use temp file + rename pattern for atomic append
            # Write content to temp file, then rename to append to target
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=f'.tmp_{operation_id}_',
                dir=filepath.parent,
                prefix='.tmp_append_'
            )
            temp_path_obj = Path(temp_path)

            try:
                # Write content to temp file
                if mode == 'a':
                    _write_all(temp_fd, content.encode('utf-8'))
                else:  # 'ab'
                    _write_all(temp_fd, content)

                # Sync to disk
                os.fsync(temp_fd)

                # Close temp file
                os.close(temp_fd)
                temp_fd = None

                # Atomic rename: temp -> target (appends if target exists)
                # Note: os.replace() overwrites, so we need a different approach
                # For true atomic append, we read entire file, append, then write atomically
                if filepath.exists():
                    # Read existing content
                    existing_content = filepath.read_bytes() if mode == 'ab' else filepath.read_text()

                    # Append new content
                    if mode == 'ab':
                        combined = existing_content + content
                    else:
                        combined = existing_content + content

                    # Write combined content atomically
                    _atomic_write_impl(
                        filepath, combined, 'wb' if mode == 'ab' else 'w',
                        operation_id, False, None, True, None
                    )
                else:
                    # File doesn't exist, just rename temp file
                    os.replace(temp_path, filepath)

                # If the target already existed, the combined snapshot was
                # published by _atomic_write_impl and this staging file is no
                # longer needed. Cleanup is scoped to this operation's path.
                # Publishing is the commit point.  If staging-file cleanup is
                # blocked or races with another owner, retain the successful
                # append result and log the actionable failure instead of
                # retrying the append and duplicating the record.
                _cleanup_temp_path(
                    temp_path_obj,
                    operation_id,
                    "successful atomic append",
                )

                logger.info(f"[{operation_id}] Atomic append successful to {filepath}")

            except BaseException:
                # Cleanup temp file on error with enhanced atomic append failure handling
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except OSError as close_error:
                        logger.warning(
                            f"[{operation_id}] Failed to close temp file descriptor "
                            f"after atomic append error: {close_error}"
                        )
                _cleanup_temp_path(
                    temp_path_obj,
                    operation_id,
                    "atomic append error",
                )
                raise

            return  # Success

        except (OSError, PermissionError) as e:
            last_exception = e
            if attempt < max_retries:
                logger.info(
                    f"[{operation_id}] Retry attempt {attempt + 1}/{max_retries} for atomic append: "
                    f"{type(e).__name__}: {e}"
                )
                jittered_delay = delay * (0.5 + random.random() * 0.5)
                time.sleep(jittered_delay)
                delay *= 2.0
            else:
                logger.error(
                    f"[{operation_id}] All {max_retries} retry attempts exhausted for atomic append: "
                    f"{type(e).__name__}: {e}"
                )
                raise

    # Should never reach here
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Unexpected error in atomic append for {filepath}")
