"""
Concurrency control for parallel fetch and synthesize operations.

Provides bounded concurrency via asyncio.Semaphore to prevent overwhelming
the ZAI proxy when a single utterance fans out into many intent threads.
"""
import asyncio
import os
from logging import getLogger

logger = getLogger(__name__)


# Default concurrency limit - conservative starting point
# This can be tuned via ADC_SYNTHESIZE_CONCURRENCY_LIMIT env var
DEFAULT_SYNTHESIZE_CONCURRENCY_LIMIT = 8


class ConcurrencyLimiter:
    """
    Global concurrency limiter for synthesize operations.

    Uses an asyncio.Semaphore to bound the number of concurrent LLM calls
    to the ZAI proxy. This prevents queue pressure from breaking the <3s
    target when a rambling utterance fans out into many project threads.
    """
    def __init__(self, limit: int | None = None):
        """
        Initialize the concurrency limiter.

        Args:
            limit: Maximum concurrent synthesize calls. Defaults to
                   ADC_SYNTHESIZE_CONCURRENCY_LIMIT env var or 8.
        """
        if limit is None:
            limit = int(os.environ.get(
                "ADC_SYNTHESIZE_CONCURRENCY_LIMIT",
                str(DEFAULT_SYNTHESIZE_CONCURRENCY_LIMIT)
            ))

        self._limit = limit
        self._semaphore = asyncio.Semaphore(limit)
        logger.info(f"Initialized concurrency limiter with limit={limit}")

    @property
    def limit(self) -> int:
        """Get the concurrency limit."""
        return self._limit

    async def acquire(self) -> None:
        """
        Acquire a concurrency slot.

        Blocks if the limit has been reached, then proceeds when a slot
        becomes available.
        """
        await self._semaphore.acquire()
        logger.debug(f"Acquired concurrency slot (available={self._semaphore._value})")

    def release(self) -> None:
        """Release a concurrency slot."""
        self._semaphore.release()
        logger.debug(f"Released concurrency slot (available={self._semaphore._value})")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.release()


# Global singleton instance
_limiter: ConcurrencyLimiter | None = None


def get_concurrency_limiter() -> ConcurrencyLimiter:
    """Get or create the global concurrency limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = ConcurrencyLimiter()
    return _limiter


def reset_concurrency_limiter(limit: int | None = None) -> None:
    """
    Reset the global concurrency limiter.

    Primarily used for testing to ensure test isolation.

    Args:
        limit: New limit (uses default if None)
    """
    global _limiter
    _limiter = ConcurrencyLimiter(limit=limit)
    logger.debug(f"Reset concurrency limiter with limit={_limiter.limit}")
