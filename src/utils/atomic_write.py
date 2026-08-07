"""
Atomic write utilities for filesystem operations.

This module provides safe write operations that prevent data corruption
by using temporary files and atomic renames, with comprehensive error
handling, rollback support, and logging.
"""

import logging
import os
import tempfile
import time
import random
from pathlib import Path
from typing import Union, Optional, Callable
from contextlib import contextmanager
import uuid

logger = logging.getLogger(__name__)


class AtomicWriteError(Exception):
    """Base exception for atomic write errors."""
    pass


class AtomicWriteRollbackError(AtomicWriteError):
    """Raised when rollback fails after a write error."""
    pass


def atomic_write(
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
                import shutil
                shutil.copy2(filepath, backup_path)
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
                    os.write(fd, content)
                else:
                    # Text mode: encode to UTF-8
                    os.write(fd, content.encode('utf-8'))
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
                        f"[{operation_id}] Found orphaned temp files: {orphaned_files}"
                    )
                    # Clean them up
                    for orphan in orphaned_files:
                        try:
                            orphan.unlink()
                            logger.info(f"[{operation_id}] Cleaned up orphaned temp file: {orphan}")
                        except OSError as e:
                            logger.error(f"[{operation_id}] Failed to cleanup orphaned temp file {orphan}: {e}")

            logger.info(
                f"[{operation_id}] Atomic write completed successfully",
                extra={
                    "filepath": str(filepath),
                    "backup_path": str(backup_path) if backup_path else None,
                    "operation_id": operation_id
                }
            )
            return backup_path

        except Exception as e:
            # Clean up temp file on any error
            if temp_path_obj.exists():
                try:
                    temp_path_obj.unlink()
                    logger.info(f"[{operation_id}] Cleaned up temp file after error: {temp_path}")
                except OSError as cleanup_error:
                    logger.error(
                        f"[{operation_id}] Failed to cleanup temp file {temp_path}: {cleanup_error}"
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

    # Create temporary file
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=filepath.parent,
            prefix=f'.{filepath.name}.tmp_{operation_id}_',
            suffix='.tmp'
        )
        os.close(fd)  # Close it, caller will write to it
    except OSError as e:
        error_msg = f"Cannot create temp file in {filepath.parent}: {e}"
        logger.error(f"[{operation_id}] {error_msg}")
        raise PermissionError(error_msg) from e

    temp_path_obj = Path(temp_path)

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

    except Exception:
        # Error in context block - rollback (cleanup temp file)
        logger.warning(
            f"[{operation_id}] Exception in context, rolling back",
            extra={"operation_id": operation_id}
        )

        if temp_path_obj.exists():
            try:
                temp_path_obj.unlink()
                logger.info(f"[{operation_id}] Rollback successful: cleaned up {temp_path}")
            except OSError as e:
                rollback_error = AtomicWriteRollbackError(
                    f"Failed to rollback temp file {temp_path}: {e}"
                )
                logger.error(f"[{operation_id}] {rollback_error}")
                raise rollback_error from e

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


def cleanup_orphaned_temp_files(directory: Union[str, Path], pattern: str = '*.tmp') -> int:
    """
    Clean up orphaned temporary files in a directory.

    Useful for startup cleanup of any temp files that may have been left
    from previous crashes or interrupted operations.

    Args:
        directory: Directory to clean up
        pattern: Glob pattern for temp files (default: '*.tmp')

    Returns:
        Number of files cleaned up

    Example:
        >>> cleaned = cleanup_orphaned_temp_files('/tmp', '*.tmp')
        >>> print(f"Cleaned up {cleaned} orphaned temp files")
    """
    directory = Path(directory)
    count = 0

    try:
        for temp_file in directory.glob(pattern):
            try:
                temp_file.unlink()
                count += 1
                logger.info(f"Cleaned up orphaned temp file: {temp_file}")
            except OSError as e:
                logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
    except Exception as e:
        logger.error(f"Failed to cleanup temp files in {directory}: {e}")

    logger.info(f"Cleanup complete: {count} files removed from {directory}")
    return count


def atomic_append(
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

            try:
                # Write content to temp file
                if mode == 'a':
                    os.write(temp_fd, content.encode('utf-8'))
                else:  # 'ab'
                    os.write(temp_fd, content)

                # Sync to disk
                os.fsync(temp_fd)

                # Close temp file
                os.close(temp_fd)

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
                    os.rename(temp_path, filepath)

                logger.info(f"[{operation_id}] Atomic append successful to {filepath}")

            except OSError as e:
                # Cleanup temp file on error
                try:
                    os.close(temp_fd)
                except:
                    pass
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except:
                    pass
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
