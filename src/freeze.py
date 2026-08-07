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

    Uses atomic file operations to prevent partial state issues.

    Args:
        frozen: If True, create sentinel file; if False, remove it.

    Raises:
        OSError: If atomic operations fail
    """
    if frozen:
        # Atomic write using temp file + rename pattern
        try:
            # Ensure directory exists
            SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Create temp file with unique name in same directory
            temp_path = SENTINEL_PATH.parent / f".{SENTINEL_PATH.name}.{uuid.uuid4()}.tmp"

            # Write to temp file
            temp_path.write_text("Self-modification frozen via 'adc freeze' command\n")

            # Atomic rename to target
            temp_path.replace(SENTINEL_PATH)

            logger.info(f"Created freeze sentinel: {SENTINEL_PATH}")

        except Exception as e:
            # Clean up temp file if it exists
            if 'temp_path' in locals() and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            logger.error(f"Failed to create freeze sentinel: {e}")
            raise OSError(f"Atomic write failed for freeze sentinel: {e}") from e
    else:
        # Atomic unlink with error handling
        try:
            # Use try/except directly on unlink to avoid race condition
            SENTINEL_PATH.unlink(missing_ok=False)
            logger.info(f"Removed freeze sentinel: {SENTINEL_PATH}")
        except FileNotFoundError:
            # Already removed - this is idempotent
            logger.debug(f"Freeze sentinel already removed: {SENTINEL_PATH}")
        except Exception as e:
            logger.error(f"Failed to remove freeze sentinel: {e}")
            raise OSError(f"Failed to remove freeze sentinel: {e}") from e


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
