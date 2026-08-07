"""
Retry utilities for git operations with exponential backoff.

This module provides decorators and utilities for retrying git operations
that fail due to transient network errors (timeouts, connection issues, etc.).
"""

import asyncio
import logging
import random
import subprocess
import time
from functools import wraps
from typing import Type, Tuple, Callable, Any, Optional, List

from src.action.steps.git_validation import GitError, GitNetworkError, GitAuthenticationError, GitConflictError
from src.errors import is_transient


logger = logging.getLogger(__name__)


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.25,
    log_retries: bool = True,
):
    """
    Decorator to retry functions that fail with transient errors using exponential backoff.

    Implements exponential backoff with jitter to prevent thundering herd:
    delay = min(base_delay * 2^attempt, max_delay)
    jitter = delay * (random value in [-jitter_factor, +jitter_factor])
    final_delay = delay + jitter

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay before first retry in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
        jitter_factor: Jitter as fraction of delay, ±25% by default (default: 0.25)
        log_retries: Whether to log retry attempts (default: True)

    Returns:
        Decorated function that retries on transient errors with exponential backoff

    Example:
        @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
        async def fetch_data(url):
            async with httpx.AsyncClient() as client:
                return await client.get(url)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Check if error is transient using the classifier
                    if not is_transient(e):
                        logger.error(
                            f"Non-transient error in {func.__name__} (no retry): "
                            f"{type(e).__name__}: {e}"
                        )
                        raise

                    # Max retries exceeded
                    if attempt >= max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise

                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** attempt), max_delay)

                    # Add jitter: ±jitter_factor of the delay
                    jitter = delay * random.uniform(-jitter_factor, jitter_factor)
                    final_delay = delay + jitter

                    if log_retries:
                        logger.warning(
                            f"Transient error in {func.__name__} on attempt "
                            f"{attempt + 1}/{max_retries + 1}, "
                            f"retrying in {final_delay:.2f}s "
                            f"(base: {delay:.2f}s, jitter: {jitter:+.2f}s): "
                            f"{type(e).__name__}: {e}"
                        )

                    await asyncio.sleep(final_delay)

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Check if error is transient using the classifier
                    if not is_transient(e):
                        logger.error(
                            f"Non-transient error in {func.__name__} (no retry): "
                            f"{type(e).__name__}: {e}"
                        )
                        raise

                    # Max retries exceeded
                    if attempt >= max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise

                    # Calculate exponential backoff delay
                    delay = min(base_delay * (2 ** attempt), max_delay)

                    # Add jitter: ±jitter_factor of the delay
                    jitter = delay * random.uniform(-jitter_factor, jitter_factor)
                    final_delay = delay + jitter

                    if log_retries:
                        logger.warning(
                            f"Transient error in {func.__name__} on attempt "
                            f"{attempt + 1}/{max_retries + 1}, "
                            f"retrying in {final_delay:.2f}s "
                            f"(base: {delay:.2f}s, jitter: {jitter:+.2f}s): "
                            f"{type(e).__name__}: {e}"
                        )

                    time.sleep(final_delay)

        # Detect if function is async or sync
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Transient error patterns that should trigger retries
TRANSIENT_ERROR_PATTERNS = [
    "timeout",
    "timed out",
    "connection",
    "network",
    "unreachable",
    "dns",
    "temporarily unavailable",
    "connection reset",
    "broken pipe",
    "host unreachable",
    "network is unreachable",
    "etimedout",
    "econnreset",
    "econnrefused",
    "ehostunreach",
]


def is_transient_error(error: Exception) -> bool:
    """
    Determine if an error is transient and worth retrying.

    Args:
        error: The exception to check

    Returns:
        True if the error appears to be transient, False otherwise
    """
    error_msg = str(error).lower()

    # Check if error message matches transient patterns
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in error_msg:
            return True

    # Check specific exception types
    if isinstance(error, subprocess.TimeoutExpired):
        return True

    if isinstance(error, subprocess.CalledProcessError):
        # Check if stderr contains transient patterns
        if hasattr(error, 'stderr') and error.stderr:
            stderr_lower = error.stderr.lower()
            for pattern in TRANSIENT_ERROR_PATTERNS:
                if pattern in stderr_lower:
                    return True

    # GitNetworkError is always transient
    if isinstance(error, GitNetworkError):
        return True

    return False


def retry_on_transient_error(
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    initial_delay: float = 1.0,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    log_retries: bool = True,
):
    """
    Decorator to retry functions that fail with transient errors.

    This decorator implements exponential backoff and retries operations
    that fail due to transient network issues. It logs retry attempts
    and raises the last exception if all retries are exhausted.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Multiplier for exponential backoff (default: 1.5)
        initial_delay: Initial delay before first retry in seconds (default: 1.0)
        retry_on: Optional tuple of exception types to retry on. If None,
                 will automatically detect transient errors.
        log_retries: Whether to log retry attempts (default: True)

    Returns:
        Decorated function that retries on transient errors

    Example:
        @retry_on_transient_error(max_retries=3, backoff_factor=2.0)
        def git_push():
            subprocess.run(["git", "push", "origin", "main"])
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            wait_time = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Check if we should retry this error
                    should_retry = False

                    if retry_on:
                        # Check if error is one of the specified types
                        should_retry = isinstance(e, retry_on)
                    else:
                        # Auto-detect transient errors
                        should_retry = is_transient_error(e)

                    # Don't retry on authentication or conflict errors
                    if isinstance(e, (GitAuthenticationError, GitConflictError)):
                        should_retry = False

                    if should_retry and attempt < max_retries:
                        if log_retries:
                            logger.warning(
                                f"Transient error in {func.__name__} on attempt "
                                f"{attempt + 1}/{max_retries + 1}, "
                                f"retrying in {wait_time:.1f}s: {type(e).__name__}: {e}"
                            )
                        time.sleep(wait_time)
                        wait_time *= backoff_factor
                    elif should_retry:
                        # Max retries exceeded
                        if log_retries:
                            logger.error(
                                f"Max retries ({max_retries}) exceeded for {func.__name__}. "
                                f"Last error: {type(e).__name__}: {e}"
                            )
                        raise
                    else:
                        # Non-transient error or no retries left
                        if log_retries:
                            logger.error(
                                f"Non-transient error in {func.__name__} (no retry): "
                                f"{type(e).__name__}: {e}"
                            )
                        raise

            # Shouldn't reach here, but just in case raise the last error
            if last_error:
                raise last_error

        return wrapper
    return decorator


async def retry_on_transient_error_async(
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    initial_delay: float = 1.0,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    log_retries: bool = True,
):
    """
    Async version of retry_on_transient_error decorator.

    Uses asyncio.sleep instead of time.sleep for async functions.
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            wait_time = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Check if we should retry this error
                    should_retry = False

                    if retry_on:
                        should_retry = isinstance(e, retry_on)
                    else:
                        should_retry = is_transient_error(e)

                    # Don't retry on authentication or conflict errors
                    if isinstance(e, (GitAuthenticationError, GitConflictError)):
                        should_retry = False

                    if should_retry and attempt < max_retries:
                        if log_retries:
                            logger.warning(
                                f"Transient error in {func.__name__} on attempt "
                                f"{attempt + 1}/{max_retries + 1}, "
                                f"retrying in {wait_time:.1f}s: {type(e).__name__}: {e}"
                            )
                        await asyncio.sleep(wait_time)
                        wait_time *= backoff_factor
                    elif should_retry:
                        if log_retries:
                            logger.error(
                                f"Max retries ({max_retries}) exceeded for {func.__name__}. "
                                f"Last error: {type(e).__name__}: {e}"
                            )
                        raise
                    else:
                        if log_retries:
                            logger.error(
                                f"Non-transient error in {func.__name__} (no retry): "
                                f"{type(e).__name__}: {e}"
                            )
                        raise

            if last_error:
                raise last_error

        return wrapper
    return decorator


class RetryTracker:
    """
    Track retry statistics for monitoring and debugging.

    This class can be used to monitor retry behavior across git operations
    and provide insights into network reliability.
    """

    def __init__(self):
        self.total_attempts: int = 0
        self.total_retries: int = 0
        self.failed_operations: int = 0
        self.successful_operations: int = 0
        self.operation_history: List[dict] = []

    def record_attempt(self, operation: str, attempt: int, success: bool, error: Optional[str] = None):
        """Record a retry attempt."""
        self.total_attempts += 1
        if attempt > 0:
            self.total_retries += 1

        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1

        self.operation_history.append({
            "operation": operation,
            "attempt": attempt,
            "success": success,
            "error": error,
        })

    def get_statistics(self) -> dict:
        """Get retry statistics."""
        return {
            "total_attempts": self.total_attempts,
            "total_retries": self.total_retries,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "retry_rate": self.total_retries / self.total_attempts if self.total_attempts > 0 else 0,
        }

    def reset(self):
        """Reset all statistics."""
        self.total_attempts = 0
        self.total_retries = 0
        self.failed_operations = 0
        self.successful_operations = 0
        self.operation_history = []


# Global retry tracker instance
_retry_tracker = RetryTracker()


def get_retry_tracker() -> RetryTracker:
    """Get the global retry tracker instance."""
    return _retry_tracker
