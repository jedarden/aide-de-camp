"""
Configuration management for aide-de-camp.

Provides centralized configuration management for retry parameters and other
application settings.
"""
from .retry import (
    RetryConfig,
    get_retry_config,
    set_retry_config,
    validate_retry_config,
)

__all__ = [
    "RetryConfig",
    "get_retry_config",
    "set_retry_config",
    "validate_retry_config",
]