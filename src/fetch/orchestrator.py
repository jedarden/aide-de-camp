"""
Fetch orchestrator: coordinates concurrent fetch execution with streaming support.

Runs all fetch sources concurrently, provides incremental results via callbacks,
tracks coverage, and surfaces caveats for failed sources.
"""

import asyncio
import time
from logging import getLogger
from typing import Any, Callable, Optional

from .commands import (
    FetchContext,
    FetchCoverage,
    FetchIntent,
    FetchRequest,
    FetchResult,
    FetchSource,
    SourceResult,
    get_fetch_commands,
)
from .executor import FetchExecutor


logger = getLogger(__name__)

# Type alias for the streaming callback
# Called when a source completes: (intent_id, source, result) -> None
StreamCallback = Callable[[str, FetchSource, SourceResult], None]


class FetchOrchestrator:
    """
    Orchestrates concurrent fetch execution with streaming support.

    Features:
    - Concurrent execution of all fetch sources
    - Streaming callbacks as sources complete
    - Per-source timeout enforcement
    - Coverage tracking (succeeded, timed_out, failed, skipped)
    - Caveat generation for failed sources
    - Incremental results to synthesize strand
    """

    def __init__(self, executor: Optional[FetchExecutor] = None):
        """
        Initialize the orchestrator.

        Args:
            executor: FetchExecutor instance (uses global if not provided)
        """
        if executor is None:
            from .executor import get_fetch_executor
            self._executor = get_fetch_executor()
        else:
            self._executor = executor

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
        start_time = time.time()
        intent_id = request.intent_id
        intent_type = request.intent_type
        context = request.context

        # Get command specs for this intent type
        command_specs = get_fetch_commands(intent_type)
        if not command_specs:
            logger.warning(f"No fetch commands defined for intent type: {intent_type}")
            return self._empty_result(intent_id, intent_type)

        logger.info(
            f"Starting fetch for intent {intent_id} "
            f"(type={intent_type.value}, sources={len(command_specs)})"
        )

        # Execute all sources concurrently
        source_results: dict[FetchSource, SourceResult] = {}
        tasks = []

        for spec in command_specs:
            # Skip if we can't expand the template (missing context)
            expanded_cmd = self._try_expand_template(spec, context)
            if expanded_cmd is None:
                logger.debug(f"Skipping {spec.source}: missing context for template")
                source_results[spec.source] = SourceResult(
                    source=spec.source,
                    status="skipped",
                    data={},
                    error="Missing context for template expansion",
                )
                continue

            # Create task for this source
            task = asyncio.create_task(
                self._execute_source_with_timeout(
                    spec=spec,
                    expanded_cmd=expanded_cmd,
                    context=context,
                )
            )
            tasks.append((spec.source, task))

        # Wait for tasks with streaming callback
        for source, task in tasks:
            try:
                result = await task
                source_results[source] = result

                # Call streaming callback if provided
                if stream_callback:
                    try:
                        stream_callback(intent_id, source, result)
                    except Exception as e:
                        logger.error(f"Stream callback error for {source}: {e}")

            except Exception as e:
                logger.error(f"Task execution error for {source}: {e}")
                source_results[source] = SourceResult(
                    source=source,
                    status="error",
                    data={},
                    error=str(e),
                )

        # Calculate coverage
        coverage = self._calculate_coverage(
            total_sources=len(command_specs),
            source_results=source_results,
            command_specs=command_specs,
        )

        # Generate caveats
        caveats = self._generate_caveats(coverage, source_results)

        total_duration_ms = int((time.time() - start_time) * 1000)

        result = FetchResult(
            intent_id=intent_id,
            intent_type=intent_type,
            sources=source_results,
            coverage=coverage,
            total_duration_ms=total_duration_ms,
            caveats=caveats,
        )

        logger.info(
            f"Fetch complete for intent {intent_id}: "
            f"{coverage.success_rate:.1%} success, {total_duration_ms}ms"
        )

        return result

    def _try_expand_template(
        self,
        spec: Any,
        context: FetchContext,
    ) -> Optional[str]:
        """
        Try to expand a command template.

        Returns None if template can't be expanded (missing context).
        """
        try:
            return context.expand_template(spec.command_template)
        except KeyError as e:
            logger.debug(f"Cannot expand template for {spec.source}: missing {e}")
            return None

    async def _execute_source_with_timeout(
        self,
        spec: Any,
        expanded_cmd: str,
        context: FetchContext,
    ) -> SourceResult:
        """
        Execute a single fetch source with timeout enforcement.

        Args:
            spec: FetchCommandSpec
            expanded_cmd: Expanded command string
            context: FetchContext

        Returns:
            SourceResult with status, data, error, duration
        """
        source = spec.source
        timeout = spec.timeout_seconds

        start = time.time()

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._executor.execute_command(
                    source=source,
                    command=expanded_cmd,
                    context=context,
                ),
                timeout=timeout,
            )

            duration_ms = int((time.time() - start) * 1000)

            if result.get("error"):
                return SourceResult(
                    source=source,
                    status="error",
                    data=result.get("data", {}),
                    error=result.get("error"),
                    duration_ms=duration_ms,
                )

            return SourceResult(
                source=source,
                status="success",
                data=result.get("data", result),
                duration_ms=duration_ms,
                cached=result.get("cached", False),
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start) * 1000)
            logger.warning(f"Source {source} timed out after {timeout}s")
            return SourceResult(
                source=source,
                status="timeout",
                data={},
                error=f"Timeout after {timeout}s",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Source {source} failed: {e}")
            return SourceResult(
                source=source,
                status="error",
                data={},
                error=str(e),
                duration_ms=duration_ms,
            )

    def _calculate_coverage(
        self,
        total_sources: int,
        source_results: dict[FetchSource, SourceResult],
        command_specs: list[Any],
    ) -> FetchCoverage:
        """Calculate coverage report from source results."""
        succeeded: list[FetchSource] = []
        timed_out: list[FetchSource] = []
        failed: list[FetchSource] = []
        skipped: list[FetchSource] = []

        for source, result in source_results.items():
            if result.status == "success":
                succeeded.append(source)
            elif result.status == "timeout":
                timed_out.append(source)
            elif result.status == "error":
                failed.append(source)
            elif result.status == "skipped":
                skipped.append(source)

        # Check for required source failures
        required_sources = {cmd.source for cmd in command_specs if cmd.required}
        required_failures = [s for s in failed if s in required_sources]

        return FetchCoverage(
            total_sources=total_sources,
            succeeded=succeeded,
            timed_out=timed_out,
            failed=failed,
            skipped=skipped,
            _has_required_failure=bool(required_failures),
        )

    def _generate_caveats(
        self,
        coverage: FetchCoverage,
        source_results: dict[FetchSource, SourceResult],
    ) -> list[str]:
        """
        Generate caveat messages for failed sources.

        Caveats explain to the synthesize strand what data is missing
        and why, so it can qualify its response appropriately.
        """
        caveats = []

        # Timeout caveats
        for source in coverage.timed_out:
            result = source_results.get(source)
            caveats.append(
                f"{source.value}: {result.error if result else 'Timed out'}"
            )

        # Error caveats
        for source in coverage.failed:
            result = source_results.get(source)
            error_msg = result.error if result else "Failed"
            caveats.append(f"{source.value}: {error_msg}")

        # Skipped caveats
        for source in coverage.skipped:
            result = source_results.get(source)
            error_msg = result.error if result else "Skipped"
            caveats.append(f"{source.value}: {error_msg}")

        # Infrastructure-wide caveat
        if coverage.success_rate == 0 and coverage.total_sources > 0:
            caveats.append(
                "All fetch sources failed - infrastructure may be unreachable"
            )

        return caveats

    def _empty_result(
        self,
        intent_id: str,
        intent_type: Any,
    ) -> FetchResult:
        """Create an empty result for intents with no fetch commands."""
        coverage = FetchCoverage(
            total_sources=0,
            succeeded=[],
            timed_out=[],
            failed=[],
            skipped=[],
        )

        return FetchResult(
            intent_id=intent_id,
            intent_type=intent_type,
            sources={},
            coverage=coverage,
            total_duration_ms=0,
            caveats=["No fetch commands defined for this intent type"],
        )


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
        stream_callback: Optional callback for incremental results

    Returns:
        FetchResult with all source results
    """
    orchestrator = get_orchestrator()
    return await orchestrator.execute_fetch(request, stream_callback)
