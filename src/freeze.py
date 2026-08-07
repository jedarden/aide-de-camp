"""
Self-modification freeze mechanism.

Provides three-layer freeze protection for self-modification writes:
1. Environment variable ADC_SELFMOD_FREEZE=1
2. Sentinel file data/FREEZE
3. CLI command 'adc freeze' (toggles sentinel file)
"""

import os
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from logging import getLogger

from .utils.atomic_write import atomic_write

logger = getLogger(__name__)


# Constants
ENV_VAR_NAME = "ADC_SELFMOD_FREEZE"
SENTINEL_PATH = Path("/home/coding/aide-de-camp/data/FREEZE")


@dataclass
class FreezeStatus:
    """Status of freeze protection."""
    is_frozen: bool
    reason: Optional[str] = None  # Which freeze signal is active


def check_frozen() -> FreezeStatus:
    """
    Check if self-modification is frozen.

    Checks three freeze signals in order:
    1. Environment variable ADC_SELFMOD_FREEZE=1
    2. Sentinel file data/FREEZE existence

    Returns:
        FreezeStatus with is_frozen=True if any signal is active,
        plus reason indicating which signal is active.
    """
    # Check environment variable
    env_value = os.environ.get(ENV_VAR_NAME, "")
    if env_value == "1":
        return FreezeStatus(
            is_frozen=True,
            reason=f"env var {ENV_VAR_NAME}=1"
        )

    # Check sentinel file
    if SENTINEL_PATH.exists():
        return FreezeStatus(
            is_frozen=True,
            reason=f"sentinel file {SENTINEL_PATH}"
        )

    # Not frozen
    return FreezeStatus(is_frozen=False, reason=None)


def ensure_unfrozen() -> None:
    """
    Ensure self-modification is not frozen.

    Raises:
        RuntimeError: If frozen, with clear message indicating which signal is active.
    """
    status = check_frozen()
    if status.is_frozen:
        raise RuntimeError(f"self-mod frozen ({status.reason})")


def set_frozen(frozen: bool) -> None:
    """
    Set freeze state by creating or removing sentinel file.

    Uses atomic_write utility to prevent partial state issues.

    Args:
        frozen: If True, create sentinel file; if False, remove it.

    Raises:
        OSError: If atomic operations fail
    """
    if frozen:
        # Use atomic_write utility for atomic sentinel file creation
        try:
            content = "Self-modification frozen via 'adc freeze' command\n"
            atomic_write(SENTINEL_PATH, content)
            logger.info(f"Created freeze sentinel: {SENTINEL_PATH}")
        except (OSError, PermissionError) as e:
            # Handle atomic write failures with specific error types
            error_msg = f"Atomic write failed for freeze sentinel {SENTINEL_PATH}: {type(e).__name__}: {e}"
            logger.error(error_msg)
            raise OSError(error_msg) from e
        except (TypeError, ValueError) as e:
            # Handle content validation errors
            error_msg = f"Content validation failed for freeze sentinel: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    else:
        # Atomic unlink with idempotent error handling
        # This cleanup operation handles atomic write failures gracefully:
        # - If a prior atomic_write failed mid-operation, temp files may exist
        # - This cleanup ensures the sentinel removal completes regardless of prior write state
        # - Uses missing_ok=True for safe idempotent cleanup
        try:
            # Use missing_ok=True for idempotent cleanup (safe if file already deleted)
            SENTINEL_PATH.unlink(missing_ok=True)
            logger.info(f"Removed freeze sentinel: {SENTINEL_PATH}")

        except PermissionError as e:
            # Handle permission-specific errors with clear messaging
            # This may occur if atomic write left the file in a protected state
            error_msg = (
                f"Permission denied removing freeze sentinel {SENTINEL_PATH}. "
                f"The file may still exist from a prior atomic write operation. "
                f"Check file permissions and try again. Manual removal: 'rm {SENTINEL_PATH}'"
            )
            logger.error(error_msg)
            # Don't raise - allow operation to complete, but log clearly
            # The user can retry or manually remove the file

        except FileNotFoundError:
            # File doesn't exist - this is fine, we wanted it gone
            # Idempotent cleanup: file already removed by prior operation or atomic write cleanup
            logger.debug(f"Freeze sentinel {SENTINEL_PATH} already removed (idempotent cleanup)")

        except OSError as e:
            # Handle other OS errors with context-specific messaging
            # This may occur if atomic write left the file system in an inconsistent state
            error_msg = (
                f"Failed to remove freeze sentinel {SENTINEL_PATH}: {type(e).__name__}: {e}. "
                f"The file may still exist from a prior atomic write operation. "
                f"You can manually remove it: 'rm {SENTINEL_PATH}' or retry the operation."
            )
            logger.warning(error_msg)
            # Don't raise - allow operation to complete, but provide clear guidance


def get_status() -> dict:
    """
    Get current freeze status as dict for CLI output.

    Returns:
        Dict with 'frozen' bool and 'reason' str (or None).
    """
    status = check_frozen()
    return {
        "frozen": status.is_frozen,
        "reason": status.reason
    }
