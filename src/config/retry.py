"""
Retry configuration management.

Provides centralized retry parameter management with environment variable
support and validation. Used by utilities/retry.py for default values.
"""
import os
from dataclasses import dataclass
from typing import Optional
from logging import getLogger

logger = getLogger(__name__)


@dataclass
class RetryConfig:
    """
    Retry configuration with environment variable support.

    Environment variables:
        ADC_MAX_RETRIES: Maximum number of retry attempts (default: 3)
        ADC_RETRY_BASE_DELAY: Initial delay between retries in seconds (default: 1.0)
        ADC_RETRY_MAX_DELAY: Maximum delay between retries in seconds (default: 60.0)
        ADC_RETRY_JITTER_FACTOR: Jitter factor as a fraction of delay (default: 0.25)

    All values must be positive numbers. max_retries must be >= 0.
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_factor: float = 0.25

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.base_delay <= 0:
            raise ValueError(f"base_delay must be > 0, got {self.base_delay}")
        if self.max_delay <= 0:
            raise ValueError(f"max_delay must be > 0, got {self.max_delay}")
        if self.max_delay < self.base_delay:
            raise ValueError(
                f"max_delay ({self.max_delay}) must be >= base_delay ({self.base_delay})"
            )
        if not (0 <= self.jitter_factor <= 1):
            raise ValueError(
                f"jitter_factor must be between 0 and 1, got {self.jitter_factor}"
            )

    @classmethod
    def from_env(cls) -> 'RetryConfig':
        """
        Create RetryConfig from environment variables.

        Returns:
            RetryConfig: Configuration with values from environment or defaults
        """
        try:
            max_retries = int(os.getenv("ADC_MAX_RETRIES", "3"))
        except ValueError:
            logger.warning("Invalid ADC_MAX_RETRIES, using default: 3")
            max_retries = 3

        try:
            base_delay = float(os.getenv("ADC_RETRY_BASE_DELAY", "1.0"))
        except ValueError:
            logger.warning("Invalid ADC_RETRY_BASE_DELAY, using default: 1.0")
            base_delay = 1.0

        try:
            max_delay = float(os.getenv("ADC_RETRY_MAX_DELAY", "60.0"))
        except ValueError:
            logger.warning("Invalid ADC_RETRY_MAX_DELAY, using default: 60.0")
            max_delay = 60.0

        try:
            jitter_factor = float(os.getenv("ADC_RETRY_JITTER_FACTOR", "0.25"))
        except ValueError:
            logger.warning("Invalid ADC_RETRY_JITTER_FACTOR, using default: 0.25")
            jitter_factor = 0.25

        return cls(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter_factor=jitter_factor
        )

    def to_dict(self) -> dict:
        """Convert configuration to dictionary for logging."""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "jitter_factor": self.jitter_factor
        }


# Global configuration instance
_config: Optional[RetryConfig] = None


def get_retry_config() -> RetryConfig:
    """
    Get or create global retry configuration instance.

    Returns:
        RetryConfig: Global retry configuration
    """
    global _config
    if _config is None:
        _config = RetryConfig.from_env()
    return _config


def set_retry_config(config: RetryConfig) -> None:
    """
    Set global retry configuration (for testing or overrides).

    Args:
        config: RetryConfig instance to set as global
    """
    global _config
    _config = config


def validate_retry_config() -> None:
    """
    Validate retry configuration on startup.

    Called during application startup to ensure configuration is valid.
    Raises ValueError if configuration is invalid.
    """
    config = get_retry_config()
    try:
        # Trigger validation via __post_init__
        RetryConfig(
            max_retries=config.max_retries,
            base_delay=config.base_delay,
            max_delay=config.max_delay,
            jitter_factor=config.jitter_factor
        )
        logger.info(f"Retry configuration validated: {config.to_dict()}")
    except ValueError as e:
        logger.error(f"Invalid retry configuration: {e}")
        raise