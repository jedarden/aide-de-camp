"""
Fetch orchestrator: coordinates concurrent fetch execution with streaming support.

Runs all fetch sources concurrently, provides incremental results via callbacks,
tracks coverage, and surfaces caveats for failed sources.
"""

import time
from logging import getLogger
from typing import Callable, Optional

from .commands import (
    FetchContext,
    FetchCoverage,
    FetchRequest,
    FetchResult,
    FetchSource,
    IntentType,
    get_fetch_commands,
    get_required_sources,
    SourceResult,
)
from .strand import FetchStrand


logger = getLogger(__name__)

# Type alias for the streaming callback
# Called when a source completes: (source, result) -> None
StreamCallback = Callable[[FetchSource, SourceResult], None]


class FetchOrchestrator:
    """
    Orchestrates concurrent fetch execution with streaming support.

    This is a thin wrapper around FetchStrand that provides the same interface
    but uses the strand's built-in concurrent execution and streaming support.

    Features:
    - Concurrent execution of all fetch sources
    - Streaming callbacks as sources complete
    - Per-source timeout enforcement
    - Coverage tracking (succeeded, timed_out, failed, skipped)
    - Caveat generation for failed sources
    """

    def __init__(self, fetch_strand: Optional[FetchStrand] = None):
        """
        Initialize the orchestrator.

        Args:
            fetch_strand: FetchStrand instance (uses global if not provided)
        """
        if fetch_strand is None:
            self._strand = FetchStrand()
        else:
            self._strand = fetch_strand

    async def execute_fetch(
        self,
        request: FetchRequest,
        stream_callback: Optional[StreamCallback] = None,
    ) -> FetchResult:
        """
        Execute a fetch request with concurrent source execution.

        Args:
            request: The fetch request with intent type and context
            stream_callback: Optional callback for incremental results

        Returns:
            FetchResult with all source results and coverage info
        """
        logger.info(
            f"Starting fetch for intent {request.intent_id} "
            f"(type={request.intent_type.value})"
        )

        # Delegate to FetchStrand which already handles:
        # - Concurrent execution
        # - Per-source timeouts
        # - Streaming callbacks
        # - Coverage tracking
        result = await self._strand.fetch(
            request=request,
            on_partial_result=stream_callback,
        )

        logger.info(
            f"Fetch complete for intent {request.intent_id}: "
            f"{result.coverage.success_rate:.1%} success, "
            f"{result.total_duration_ms}ms"
        )

        return result


# Global orchestrator instance
_orchestrator: Optional[FetchOrchestrator] = None


def get_orchestrator() -> FetchOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = FetchOrchestrator()
    return _orchestrator


async def execute_fetch(
    request: FetchRequest,
    stream_callback: Optional[StreamCallback] = None,
) -> FetchResult:
    """
    Convenience function to execute a fetch request.

    Args:
        request: The fetch request
        stream_callback: Optional callback for incremental results (receives source, result)

    Returns:
        FetchResult with all source results
    """
    orchestrator = get_orchestrator()
    return await orchestrator.execute_fetch(request, stream_callback)
