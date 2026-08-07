"""
Retry utility with exponential backoff for transient-failure-prone operations.

Provides decorators and helper functions for retrying operations that may fail
transiently due to network issues, file locks, or other intermittent problems.
"""
import asyncio
import functools
import logging
from typing import Callable, Type, Tuple, Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 0.1,  # 100ms
    max_delay: float = 1.0,    # 1 second
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Callable:
    """
    Retry decorator with exponential backoff for transient failures.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay between retries in seconds (default: 0.1s)
        max_delay: Maximum delay between retries in seconds (default: 1.0s)
        exceptions: Tuple of exception types to catch and retry on
        on_retry: Optional callback function called on each retry attempt

    Returns:
        Decorator function that wraps the target function with retry logic

    Example:
        @retry_with_exponential_backoff(
            max_retries=3,
            base_delay=0.1,
            max_delay=1.0,
            exceptions=(sqlite3.OperationalError, asyncio.TimeoutError)
        )
        async def fetch_data():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            """Async wrapper for retry logic."""
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (2 ** attempt), max_delay)

                        logger.warning(
                            f"Retry attempt {attempt + 1}/{max_retries} "
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
                            f"All {max_retries} retry attempts exhausted "
                            f"for {func.__name__}. Final error: {str(e)[:100]}"
                        )

            # If we get here, all retries failed
            raise last_exception  # type: ignore

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            """Synchronous wrapper for retry logic."""
            import time

            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (2 ** attempt), max_delay)

                        logger.warning(
                            f"Retry attempt {attempt + 1}/{max_retries} "
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
                            f"All {max_retries} retry attempts exhausted "
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
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any
) -> T:
    """
    Helper function to execute an async function with retry logic.

    Args:
        func: Async function to execute
        *args: Positional arguments to pass to the function
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
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
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)

                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries} "
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
                    f"All {max_retries} retry attempts exhausted "
                    f"for {func.__name__}. Final error: {str(e)[:100]}"
                )

    raise last_exception  # type: ignore


def retry_sync(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any
) -> T:
    """
    Helper function to execute a synchronous function with retry logic.

    Args:
        func: Synchronous function to execute
        *args: Positional arguments to pass to the function
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
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
    import time

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)

                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries} "
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
                    f"All {max_retries} retry attempts exhausted "
                    f"for {func.__name__}. Final error: {str(e)[:100]}"
                )

    raise last_exception  # type: ignore


class RetryContext:
    """
    Context manager for retry logic with manual control.

    Useful for complex retry scenarios where you need to execute
    multiple operations with shared retry state.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 1.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
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

                if self.attempt_count < self.max_retries:
                    delay = min(self.base_delay * (2 ** self.attempt_count), self.max_delay)

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
                    delay = min(self.base_delay * (2 ** self.attempt_count), self.max_delay)

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
