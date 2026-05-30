"""
Pre-warmed context module.

Exports the ContextWarmer class and related types.
"""

from .warmer import (
    ContextWarmer,
    ContextBundle,
    DEFAULT_CONTEXT_TTL,
    DEFAULT_REFRESH_INTERVAL,
    get_context_warmer,
)
from .prefetch import (
    SpeculativePrefetcher,
    FollowUpPattern,
    PrefetchPrediction,
    PrefetchCache,
    get_prefetcher,
)

__all__ = [
    "ContextWarmer",
    "ContextBundle",
    "DEFAULT_CONTEXT_TTL",
    "DEFAULT_REFRESH_INTERVAL",
    "get_context_warmer",
    "SpeculativePrefetcher",
    "FollowUpPattern",
    "PrefetchPrediction",
    "PrefetchCache",
    "get_prefetcher",
]
