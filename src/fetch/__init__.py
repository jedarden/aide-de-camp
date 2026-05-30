"""
Fetch strand: concurrent data fetching with streaming support.

Provides deterministic command execution per intent type with:
- Concurrent fetching of all sources
- Streaming support for partial results
- Coverage tracking (success/failure/timeout per source)
- Per-source timeout handling
"""

from .strand import FetchStrand, get_fetch_strand
from .commands import (
    FetchContext,
    FetchCoverage,
    FetchRequest,
    FetchResult,
    FetchSource,
    IntentType,
    SourceResult,
    get_fetch_commands,
    get_required_sources,
)
from .orchestrator import FetchOrchestrator, execute_fetch, get_orchestrator

# Re-export for backward compatibility
from .executor import FetchExecutor, FetchCommand, get_fetch_executor

__all__ = [
    # New fetch strand API
    "FetchStrand",
    "get_fetch_strand",
    "FetchContext",
    "FetchRequest",
    "FetchResult",
    "FetchCoverage",
    "FetchSource",
    "IntentType",
    "SourceResult",
    "get_fetch_commands",
    "get_required_sources",
    # Orchestrator API
    "FetchOrchestrator",
    "execute_fetch",
    "get_orchestrator",
    # Legacy executor API
    "FetchExecutor",
    "FetchCommand",
    "get_fetch_executor",
]
