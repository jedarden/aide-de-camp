"""
Fetch strand: concurrent data fetching with streaming support.

Provides deterministic command execution per intent type with:
- Concurrent fetching of all sources
- Streaming support for partial results
- Coverage tracking (success/failure/timeout per source)
- Per-source timeout handling

Architecture:
- commands.py: Intent types, fetch sources, command matrix, data structures
- orchestrator.py: Full implementation with FetchStrand, concurrent execution, and coverage tracking

This is the single canonical fetch implementation. The legacy executor.py
has been removed - all code now uses this stack.
"""

from .commands import (
    KUBECTL_PROXIES,  # Exported for escalate/commands.py
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
from .orchestrator import (
    FetchOrchestrator,
    FetchStrand,
    execute_fetch,
    get_fetch_strand,
    get_orchestrator,
)

__all__ = [
    # Constants
    "KUBECTL_PROXIES",
    # Fetch strand API
    "FetchStrand",
    "get_fetch_strand",
    # Data structures
    "FetchContext",
    "FetchRequest",
    "FetchResult",
    "FetchCoverage",
    "FetchSource",
    "IntentType",
    "SourceResult",
    # Utilities
    "get_fetch_commands",
    "get_required_sources",
    # Orchestrator API (convenience wrapper)
    "FetchOrchestrator",
    "execute_fetch",
    "get_orchestrator",
]
