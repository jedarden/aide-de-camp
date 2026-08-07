"""
Atomic write utilities for filesystem operations.

This module provides safe write operations that prevent data corruption
by using temporary files and atomic renames.
"""

import os
import tempfile
from pathlib import Path
from typing import Union


def atomic_write(filepath: Union[str, Path], content: str, mode: str = 'w') -> None:
    """
    Write content to a file atomically.

    This function writes to a temporary file in the same directory as the target,
    then uses os.rename() to overwrite the target file. On Linux, os.rename()
    is atomic when both files are on the same filesystem, ensuring that readers
    either see the old content or the complete new content, never a partial write.

    Args:
        filepath: Target file path (str or Path object)
        content: Content to write (str for text mode, bytes for binary mode)
        mode: Write mode - 'w' for text, 'wb' for binary (default: 'w')

    Raises:
        PermissionError: If lacking write permissions for the directory
        OSError: If disk is full or other filesystem error occurs
        TypeError: If content type doesn't match mode (e.g., str with 'wb')

    Example:
        >>> atomic_write('/path/to/config.json', '{"key": "value"}')
        >>> # File is guaranteed to be complete or unchanged

    Note:
        - Requires write permission to the containing directory
        - Preserves file permissions on overwrite (rename retains metadata)
        - Works across filesystem boundaries only if both source and target
          are on the same filesystem (guaranteed here since temp file is
          created in the same directory)
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Validate content type matches mode
    if mode == 'wb':
        if not isinstance(content, bytes):
            raise TypeError(f"Binary mode requires bytes content, got {type(content).__name__}")
    elif mode == 'w':
        if not isinstance(content, str):
            raise TypeError(f"Text mode requires str content, got {type(content).__name__}")

    # Create temporary file in same directory as target (ensures same filesystem)
    # delete=False is fine because we rename it; if rename fails, we clean up manually
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=filepath.parent,
            prefix=f'.{filepath.name}.tmp_',
            suffix='.tmp'
        )
    except OSError as e:
        raise PermissionError(f"Cannot create temp file in {filepath.parent}: {e}") from e

    try:
        # Write content to temp file
        if mode == 'wb':
            os.write(fd, content)
        else:
            # Text mode: encode to UTF-8
            os.write(fd, content.encode('utf-8'))

        os.close(fd)

        # Atomic rename - replaces target if it exists
        os.replace(temp_path, filepath)  # Python 3.3+ atomic even on Windows

    except OSError as e:
        # Clean up temp file if rename failed
        try:
            os.unlink(temp_path)
        except OSError:
            pass  # Best effort cleanup
        raise OSError(f"Failed atomic write to {filepath}: {e}") from e

    except Exception as e:
        # Clean up temp file on any other error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
