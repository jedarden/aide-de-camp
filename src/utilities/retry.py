"""
Retry utility with exponential backoff for transient-failure-prone operations.

Provides decorators and helper functions for retrying operations that may fail
transiently due to network issues, file locks, or other intermittent problems.

Supports configurable defaults via environment variables (ADC_MAX_RETRIES,
ADC_RETRY_BASE_DELAY, ADC_RETRY_MAX_DELAY, ADC_RETRY_JITTER_FACTOR) with
per-decorator override capability.

Integrates with transient_errors.py to automatically determine if an error
is transient (retry-eligible) or permanent (fail immediately).
"""
import asyncio
import functools
import logging
import random
from typing import Callable, Type, Tuple, Any, Optional, TypeVar

import httpx
import aiohttp

from src.errors.transient_errors import is_transient

logger = logging.getLogger(__name__)

T = TypeVar('T')


def calculate_delay_with_backoff(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter_factor: float
) -> float:
    """
    Calculate retry delay with exponential backoff and jitter.

    Uses exponential backoff formula: delay = base_delay * (2 ** attempt)
    The delay is capped at max_delay to prevent excessively long waits.
    Jitter is added to prevent the thundering herd problem when multiple
    processes retry simultaneously.

    Args:
        attempt: Current retry attempt number (0-indexed: 0, 1, 2, ...)
        base_delay: Initial delay in seconds (e.g., 1.0)
        max_delay: Maximum delay cap in seconds (e.g., 60.0)
        jitter_factor: Jitter as a fraction of delay, 0 to 1 (e.g., 0.25 for ±25%)

    Returns:
        float: Final delay value in seconds with exponential backoff and jitter applied

    Examples:
        >>> calculate_delay_with_backoff(0, 1.0, 60.0, 0.25)  # First retry
        ~1.0  # base_delay * 2^0 = 1.0, then jitter ±0.25

        >>> calculate_delay_with_backoff(1, 1.0, 60.0, 0.25)  # Second retry
        ~2.0  # base_delay * 2^1 = 2.0, then jitter ±0.5

        >>> calculate_delay_with_backoff(10, 1.0, 60.0, 0.25)  # Cap at max
        ~60.0  # base_delay * 2^10 = 1024, capped at 60.0, then jitter ±15.0
    """
    # Calculate exponential backoff: base_delay * (2 ** attempt)
    delay = base_delay * (2 ** attempt)

    # Cap at max_delay to prevent excessive delays
    if delay > max_delay:
        delay = max_delay

    # Add jitter: delay ± (delay * jitter_factor)
    jitter = delay * jitter_factor
    final_delay = delay + random.uniform(-jitter, jitter)

    # Ensure delay is non-negative (jitter could theoretically make it negative)
    return max(0.0, final_delay)


def _apply_jitter(delay: float, jitter_factor: float) -> float:
    """
    Apply jitter to a delay value.

    Adds random jitter to prevent thundering herd problem when multiple
    processes retry simultaneously.

    Args:
        delay: Base delay value in seconds
        jitter_factor: Jitter as a fraction of delay (0 to 1)

    Returns:
        float: Delay with jitter applied
    """
    if jitter_factor <= 0:
        return delay
    if jitter_factor >= 1:
        # Full jitter: random between 0 and delay
        return delay * random.random()
    # Partial jitter: delay ± (jitter_factor * delay)
    jitter = delay * jitter_factor
    return delay + random.uniform(-jitter, jitter)


def retry_with_exponential_backoff(
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter_factor: Optional[float] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Callable:
    """
    Retry decorator with exponential backoff and jitter for transient failures.

    Parameters default to environment-configured values (ADC_MAX_RETRIES,
    ADC_RETRY_BASE_DELAY, ADC_RETRY_MAX_DELAY, ADC_RETRY_JITTER_FACTOR)
    unless explicitly overridden.

    Args:
        max_retries: Maximum number of retry attempts (None = use config)
        base_delay: Initial delay between retries in seconds (None = use config)
        max_delay: Maximum delay between retries in seconds (None = use config)
        jitter_factor: Jitter factor as fraction of delay, 0 to 1 (None = use config)
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called on each retry attempt

    Returns:
        Decorator function that wraps the target function with retry logic

    Example:
        # Use configured defaults
        @retry_with_exponential_backoff()
        async def fetch_data():
            ...

        # Override specific parameters
        @retry_with_exponential_backoff(max_retries=5, base_delay=2.0)
        async def fetch_data():
            ...

        # Override with exceptions
        @retry_with_exponential_backoff(
            exceptions=(sqlite3.OperationalError, asyncio.TimeoutError)
        )
        async def fetch_data():
            ...
    """
    # Import here to avoid circular dependency
    from src.config.retry import get_retry_config

    # Load configuration defaults for any None values
    config = get_retry_config()
    effective_max_retries = max_retries if max_retries is not None else config.max_retries
    effective_base_delay = base_delay if base_delay is not None else config.base_delay
    effective_max_delay = max_delay if max_delay is not None else config.max_delay
    effective_jitter = jitter_factor if jitter_factor is not None else config.jitter_factor

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            """Async wrapper for retry logic."""
            last_exception = None

            for attempt in range(effective_max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Only check transience for network-related exceptions
                    # Generic exceptions (ValueError, etc.) should always be retried if specified
                    network_error_types = (httpx.HTTPError, aiohttp.ClientError, OSError, TimeoutError)
                    if isinstance(e, network_error_types) and not is_transient(e):
                        logger.error(
                            f"Non-transient error in {func.__name__} - failing immediately. "
                            f"Error: {str(e)[:100]}"
                        )
                        raise

                    if attempt < effective_max_retries:
                        # Calculate delay with exponential backoff and jitter
                        delay = calculate_delay_with_backoff(
                            attempt=attempt,
                            base_delay=effective_base_delay,
                            max_delay=effective_max_delay,
                            jitter_factor=effective_jitter
                        )

                        logger.warning(
                            f"Retry attempt {attempt + 1}/{effective_max_retries} "
                            f"for {func.__name__} after {delay:.2f}s delay. "
                            f"Error: {str(e)[:100]}"
                        )

                        # Call custom retry callback if provided
                        if on_retry:
                            try:
                                on_retry(attempt + 1, e)
                            except Exception as callback_error:
                                logger.error(
                                    f"Retry callback error: {callback_error}"
                                )

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {effective_max_retries} retry attempts exhausted "
                            f"for {func.__name__}. Final error: {str(e)[:100]}"
                        )

            # If we get here, all retries failed
            raise last_exception  # type: ignore

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            """Synchronous wrapper for retry logic."""
            import time

            last_exception = None

            for attempt in range(effective_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Only check transience for network-related exceptions
                    # Generic exceptions (ValueError, etc.) should always be retried if specified
                    network_error_types = (httpx.HTTPError, aiohttp.ClientError, OSError, TimeoutError)
                    if isinstance(e, network_error_types) and not is_transient(e):
                        logger.error(
                            f"Non-transient error in {func.__name__} - failing immediately. "
                            f"Error: {str(e)[:100]}"
                        )
                        raise

                    if attempt < effective_max_retries:
                        # Calculate delay with exponential backoff and jitter
                        delay = calculate_delay_with_backoff(
                            attempt=attempt,
                            base_delay=effective_base_delay,
                            max_delay=effective_max_delay,
                            jitter_factor=effective_jitter
                        )

                        logger.warning(
                            f"Retry attempt {attempt + 1}/{effective_max_retries} "
                            f"for {func.__name__} after {delay:.2f}s delay. "
                            f"Error: {str(e)[:100]}"
                        )

                        # Call custom retry callback if provided
                        if on_retry:
                            try:
                                on_retry(attempt + 1, e)
                            except Exception as callback_error:
                                logger.error(
                                    f"Retry callback error: {callback_error}"
                                )

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {effective_max_retries} retry attempts exhausted "
                            f"for {func.__name__}. Final error: {str(e)[:100]}"
                        )

            # If we get here, all retries failed
            raise last_exception  # type: ignore

        # Return appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def retry_async(
    func: Callable[..., T],
    *args: Any,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter_factor: Optional[float] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any
) -> T:
    """
    Helper function to execute an async function with retry logic.

    Parameters default to environment-configured values unless explicitly overridden.

    Args:
        func: Async function to execute
        *args: Positional arguments to pass to the function
        max_retries: Maximum number of retry attempts (None = use config)
        base_delay: Initial delay between retries in seconds (None = use config)
        max_delay: Maximum delay between retries in seconds (None = use config)
        jitter_factor: Jitter factor as fraction of delay, 0 to 1 (None = use config)
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called on each retry attempt
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function execution

    Example:
        result = await retry_async(
            fetch_from_database,
            query,
            max_retries=3,
            exceptions=(sqlite3.OperationalError,)
        )
    """
    # Import here to avoid circular dependency
    from src.config.retry import get_retry_config

    # Load configuration defaults for any None values
    config = get_retry_config()
    effective_max_retries = max_retries if max_retries is not None else config.max_retries
    effective_base_delay = base_delay if base_delay is not None else config.base_delay
    effective_max_delay = max_delay if max_delay is not None else config.max_delay
    effective_jitter = jitter_factor if jitter_factor is not None else config.jitter_factor

    last_exception = None

    for attempt in range(effective_max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            # Only check transience for network-related exceptions
            # Generic exceptions (ValueError, etc.) should always be retried if specified
            network_error_types = (httpx.HTTPError, aiohttp.ClientError, OSError, TimeoutError)
            if isinstance(e, network_error_types) and not is_transient(e):
                logger.error(
                    f"Non-transient error in {func.__name__} - failing immediately. "
                    f"Error: {str(e)[:100]}"
                )
                raise

            if attempt < effective_max_retries:
                delay = calculate_delay_with_backoff(
                    attempt=attempt,
                    base_delay=effective_base_delay,
                    max_delay=effective_max_delay,
                    jitter_factor=effective_jitter
                )

                logger.warning(
                    f"Retry attempt {attempt + 1}/{effective_max_retries} "
                    f"for {func.__name__} after {delay:.2f}s delay. "
                    f"Error: {str(e)[:100]}"
                )

                if on_retry:
                    try:
                        on_retry(attempt + 1, e)
                    except Exception as callback_error:
                        logger.error(f"Retry callback error: {callback_error}")

                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"All {effective_max_retries} retry attempts exhausted "
                    f"for {func.__name__}. Final error: {str(e)[:100]}"
                )

    raise last_exception  # type: ignore


def retry_sync(
    func: Callable[..., T],
    *args: Any,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter_factor: Optional[float] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any
) -> T:
    """
    Helper function to execute a synchronous function with retry logic.

    Parameters default to environment-configured values unless explicitly overridden.

    Args:
        func: Synchronous function to execute
        *args: Positional arguments to pass to the function
        max_retries: Maximum number of retry attempts (None = use config)
        base_delay: Initial delay between retries in seconds (None = use config)
        max_delay: Maximum delay between retries in seconds (None = use config)
        jitter_factor: Jitter factor as fraction of delay, 0 to 1 (None = use config)
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called on each retry attempt
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function execution

    Example:
        result = retry_sync(
            read_file,
            path,
            max_retries=3,
            exceptions=(IOError, OSError)
        )
    """
    # Import here to avoid circular dependency
    from src.config.retry import get_retry_config

    # Load configuration defaults for any None values
    config = get_retry_config()
    effective_max_retries = max_retries if max_retries is not None else config.max_retries
    effective_base_delay = base_delay if base_delay is not None else config.base_delay
    effective_max_delay = max_delay if max_delay is not None else config.max_delay
    effective_jitter = jitter_factor if jitter_factor is not None else config.jitter_factor

    import time

    last_exception = None

    for attempt in range(effective_max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            # Only check transience for network-related exceptions
            # Generic exceptions (ValueError, etc.) should always be retried if specified
            network_error_types = (httpx.HTTPError, aiohttp.ClientError, OSError, TimeoutError)
            if isinstance(e, network_error_types) and not is_transient(e):
                logger.error(
                    f"Non-transient error in {func.__name__} - failing immediately. "
                    f"Error: {str(e)[:100]}"
                )
                raise

            if attempt < effective_max_retries:
                delay = calculate_delay_with_backoff(
                    attempt=attempt,
                    base_delay=effective_base_delay,
                    max_delay=effective_max_delay,
                    jitter_factor=effective_jitter
                )

                logger.warning(
                    f"Retry attempt {attempt + 1}/{effective_max_retries} "
                    f"for {func.__name__} after {delay:.2f}s delay. "
                    f"Error: {str(e)[:100]}"
                )

                if on_retry:
                    try:
                        on_retry(attempt + 1, e)
                    except Exception as callback_error:
                        logger.error(f"Retry callback error: {callback_error}")

                time.sleep(delay)
            else:
                logger.error(
                    f"All {effective_max_retries} retry attempts exhausted "
                    f"for {func.__name__}. Final error: {str(e)[:100]}"
                )

    raise last_exception  # type: ignore


class RetryContext:
    """
    Context manager for retry logic with manual control.

    Useful for complex retry scenarios where you need to execute
    multiple operations with shared retry state.

    Parameters default to environment-configured values unless explicitly overridden.
    """

    def __init__(
        self,
        max_retries: Optional[int] = None,
        base_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        jitter_factor: Optional[float] = None,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        # Import here to avoid circular dependency
        from src.config.retry import get_retry_config

        # Load configuration defaults for any None values
        config = get_retry_config()
        self.max_retries = max_retries if max_retries is not None else config.max_retries
        self.base_delay = base_delay if base_delay is not None else config.base_delay
        self.max_delay = max_delay if max_delay is not None else config.max_delay
        self.jitter_factor = jitter_factor if jitter_factor is not None else config.jitter_factor
        self.exceptions = exceptions
        self.attempt_count = 0
        self.last_exception: Optional[Exception] = None

    async def __aenter__(self):
        self.attempt_count = 0
        self.last_exception = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def __enter__(self):
        self.attempt_count = 0
        self.last_exception = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute_async(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute an async function within the retry context."""
        for self.attempt_count in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                # Clear last_exception on success
                self.last_exception = None
                return result
            except self.exceptions as e:
                self.last_exception = e

                # Only check transience for network-related exceptions
                # Generic exceptions (ValueError, etc.) should always be retried if specified
                network_error_types = (httpx.HTTPError, aiohttp.ClientError, OSError, TimeoutError)
                if isinstance(e, network_error_types) and not is_transient(e):
                    logger.error(
                        f"Non-transient error in {func.__name__} - failing immediately. "
                        f"Error: {str(e)[:100]}"
                    )
                    raise

                if self.attempt_count < self.max_retries:
                    delay = calculate_delay_with_backoff(
                        attempt=self.attempt_count,
                        base_delay=self.base_delay,
                        max_delay=self.max_delay,
                        jitter_factor=self.jitter_factor
                    )

                    logger.warning(
                        f"Retry attempt {self.attempt_count + 1}/{self.max_retries} "
                        f"for {func.__name__} after {delay:.2f}s delay. "
                        f"Error: {str(e)[:100]}"
                    )

                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries} retry attempts exhausted "
                        f"for {func.__name__}. Final error: {str(e)[:100]}"
                    )

        raise self.last_exception  # type: ignore

    def execute_sync(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute a sync function within the retry context."""
        import time

        for self.attempt_count in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                # Clear last_exception on success
                self.last_exception = None
                return result
            except self.exceptions as e:
                self.last_exception = e

                if self.attempt_count < self.max_retries:
                    delay = calculate_delay_with_backoff(
                        attempt=self.attempt_count,
                        base_delay=self.base_delay,
                        max_delay=self.max_delay,
                        jitter_factor=self.jitter_factor
                    )

                    logger.warning(
                        f"Retry attempt {self.attempt_count + 1}/{self.max_retries} "
                        f"for {func.__name__} after {delay:.2f}s delay. "
                        f"Error: {str(e)[:100]}"
                    )

                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries} retry attempts exhausted "
                        f"for {func.__name__}. Final error: {str(e)[:100]}"
                    )

        raise self.last_exception  # type: ignore
