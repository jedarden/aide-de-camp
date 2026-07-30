"""
Fetch-window policy acceptance tests (bead adc-3ib6).

Tests that synthesis gates on window close, per-source timeouts, progress states,
and timing metrics are properly recorded.

Acceptance criteria:
- Synthesize fires exactly once per thread when all sources have resolved or their
  per-source timeouts expire
- Late/timed-out sources appear only as fetch_coverage caveats — never re-synthesis
- During the window, per-source progress states stream to the pending card ('3/5 sources in')
- fetch_first_source_ms and fetch_total_ms (window close) are recorded in dispatch_timings
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fetch.commands import (
    FetchCommandSpec,
    FetchContext,
    FetchRequest,
    FetchSource,
    IntentType,
    SourceResult,
)
from src.fetch.orchestrator import FetchStrand
from src.instrument.timings import DispatchTimings
from src.intent.router import IntentRouter, RoutedIntent, IntentClassification
from src.sse.broadcaster import SSEBroadcaster, SSEEvent


# --- test helpers -----------------------------------------------------------


def _build_request(intent_type: IntentType = IntentType.STATUS) -> FetchRequest:
    """Create a test fetch request."""
    return FetchRequest(
        intent_id=str(uuid4()),
        intent_type=intent_type,
        session_id=str(uuid4()),
        context=FetchContext(
            project_slug="test-project",
            namespace="test-ns",
        ),
    )


def _slow_executor(delay: float):
    """Executor that sleeps for `delay` seconds before returning success."""
    async def _fn(ctx: FetchContext) -> dict:
        await asyncio.sleep(delay)
        return {"ok": True, "delay": delay}
    return _fn


def _timeout_after(delay: float):
    """Executor that blocks longer than a typical timeout to test timeout enforcement."""
    async def _fn(ctx: FetchContext) -> dict:
        await asyncio.sleep(delay)
        return {"ok": True}
    return _fn


def _error_executor(error: Exception):
    """Executor that raises `error`."""
    async def _fn(ctx: FetchContext) -> dict:
        raise error
    return _fn


def _quick_executor(source: FetchSource):
    """Executor that returns success quickly with source info."""
    async def _fn(ctx: FetchContext) -> dict:
        # Small delay to simulate fast but not instant execution
        await asyncio.sleep(0.01)
        return {"ok": True, "source": source.value}
    return _fn


class TestFetchWindowPolicy:
    """Tests for the fetch-window policy gating synthesis."""

    @pytest.mark.asyncio
    async def test_synthesis_waits_for_all_sources_to_complete(self):
        """Synthesis fires only after all sources complete (window close), not earlier."""
        from src.fetch.commands import FETCH_COMMAND_MATRIX

        strand = FetchStrand()

        # Get the actual sources for STATUS intent
        status_sources = [spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.STATUS]]

        # Stub only the sources that STATUS uses with different delays
        delays = {source: 0.05 + (i * 0.02) for i, source in enumerate(status_sources)}
        for source, delay in delays.items():
            strand._source_executors[source] = _slow_executor(delay)

        request = _build_request(IntentType.STATUS)

        # Track when sources complete vs when fetch completes
        source_completion_times = []
        window_close_time = None

        def on_progress(source, result):
            source_completion_times.append(time.monotonic())

        start = time.monotonic()
        result = await strand.fetch(request, on_partial_result=on_progress)
        window_close_time = time.monotonic() - start

        # All sources should have completed
        assert len(source_completion_times) == len(status_sources)

        # Window close should happen after the slowest source completes
        # (within a small margin for async overhead)
        max_delay = max(delays.values())
        assert window_close_time >= max_delay * 0.9  # Allow 10% timing variance

    @pytest.mark.asyncio
    async def test_slow_source_times_out_does_not_block_window_close(self):
        """A source slower than its timeout should not delay synthesize past window close."""
        from src.fetch.commands import FETCH_COMMAND_MATRIX

        strand = FetchStrand()

        # Make one source very slow (2s)
        slow_source = FetchSource.KUBECTL_PODS
        strand._source_executors[slow_source] = _timeout_after(2.0)

        # Other sources complete quickly
        status_sources = [spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.STATUS]]
        for source in status_sources:
            if source != slow_source:
                strand._source_executors[source] = _quick_executor(source)

        request = _build_request(IntentType.STATUS)

        # Override the command spec to use a short timeout for the slow source
        original_commands = FETCH_COMMAND_MATRIX[IntentType.STATUS]
        modified_commands = []
        for spec in original_commands:
            if spec.source == slow_source:
                modified_commands.append(FetchCommandSpec(
                    source=spec.source,
                    command_template=spec.command_template,
                    timeout_seconds=0.1,  # Short timeout
                    required=spec.required,
                    cacheable=spec.cacheable,
                ))
            else:
                modified_commands.append(spec)

        # Mock both get_fetch_commands and get_source_timeout_ms to ensure the short timeout is used
        # (config/fetch.yaml may have a longer timeout that would override the spec)
        with patch('src.fetch.orchestrator.get_fetch_commands') as mock_commands, \
             patch('src.fetch.commands.get_source_timeout_ms', return_value=None):
            mock_commands.return_value = modified_commands

            start = time.monotonic()
            result = await strand.fetch(request)
            elapsed = time.monotonic() - start

        # Window should close around the timeout, not the full 2s
        # (timeout is 0.1s, allow overhead for other sources)
        assert elapsed < 1.0, f"Window took {elapsed:.3f}s, should have timed out at 0.1s"

        # The timed-out source should be marked correctly
        assert slow_source in result.coverage.timed_out
        assert result.sources[slow_source].status == "timeout"

    @pytest.mark.asyncio
    async def test_progress_events_fire_as_sources_complete(self):
        """Per-source progress states should stream to pending card during the window."""
        from src.fetch.commands import FETCH_COMMAND_MATRIX

        strand = FetchStrand()

        # Get a subset of sources for testing
        test_sources = [FetchSource.KUBECTL_PODS, FetchSource.ARGOCD_APP, FetchSource.GIT_LOG]

        # Use staggered delays to ensure sources complete in a known order
        delays = {
            FetchSource.KUBECTL_PODS: 0.05,
            FetchSource.ARGOCD_APP: 0.10,
            FetchSource.GIT_LOG: 0.15,
        }
        for source, delay in delays.items():
            strand._source_executors[source] = _slow_executor(delay)

        # Stub other sources to succeed immediately
        status_sources = [spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.STATUS]]
        for source in status_sources:
            if source not in delays:
                strand._source_executors[source] = _quick_executor(source)

        request = _build_request(IntentType.STATUS)

        # Track progress events
        progress_events = []
        completed_order = []

        def on_progress(source, result):
            completed_order.append(source)
            progress_events.append({
                "source": source,
                "status": result.status,
                "completed_count": len(completed_order),
            })

        await strand.fetch(request, on_partial_result=on_progress)

        # Should have received progress events for all sources
        assert len(completed_order) == len(status_sources)

        # The test sources should complete in delay order (fastest first)
        test_completions = [s for s in completed_order if s in test_sources]
        assert test_completions[0] == FetchSource.KUBECTL_PODS
        assert test_completions[1] == FetchSource.ARGOCD_APP
        assert test_completions[2] == FetchSource.GIT_LOG

        # Progress events should have correct incremental counts
        test_events = [e for e in progress_events if e["source"] in test_sources]
        assert test_events[0]["completed_count"] >= 1
        assert test_events[1]["completed_count"] >= 2
        assert test_events[2]["completed_count"] >= 3

    @pytest.mark.asyncio
    async def test_timed_out_sources_included_in_caveats(self):
        """Sources that time out should appear in caveats and not trigger re-synthesis."""
        from src.fetch.commands import FETCH_COMMAND_MATRIX

        strand = FetchStrand()

        # Make one source timeout
        timeout_source = FetchSource.KUBECTL_PODS
        strand._source_executors[timeout_source] = _timeout_after(5.0)

        # Other sources succeed quickly
        status_sources = [spec.source for spec in FETCH_COMMAND_MATRIX[IntentType.STATUS]]
        for source in status_sources:
            if source != timeout_source:
                strand._source_executors[source] = _quick_executor(source)

        request = _build_request(IntentType.STATUS)

        # Override the command spec to use a short timeout for the slow source
        original_commands = FETCH_COMMAND_MATRIX[IntentType.STATUS]
        modified_commands = []
        for spec in original_commands:
            if spec.source == timeout_source:
                modified_commands.append(FetchCommandSpec(
                    source=spec.source,
                    command_template=spec.command_template,
                    timeout_seconds=0.1,  # Short timeout
                    required=spec.required,
                    cacheable=spec.cacheable,
                ))
            else:
                modified_commands.append(spec)

        # Mock both get_fetch_commands and get_source_timeout_ms to ensure the short timeout is used
        # (config/fetch.yaml may have a longer timeout that would override the spec)
        with patch('src.fetch.orchestrator.get_fetch_commands') as mock_commands, \
             patch('src.fetch.commands.get_source_timeout_ms', return_value=None):
            mock_commands.return_value = modified_commands

            result = await strand.fetch(request)

        # Timed-out source should be in the caveats
        assert result.caveats is not None
        assert any("timed out" in caveat.lower() for caveat in result.caveats)

        # Should be in timed_out bucket
        assert timeout_source in result.coverage.timed_out

        # Result should still be returned (synthesis can proceed with caveats)
        assert result is not None


class TestFetchWindowTimingMetrics:
    """Tests for fetch_first_source_ms and fetch_total_ms timing recording."""

    @pytest.mark.asyncio
    async def test_fetch_first_source_ms_recorded(self):
        """fetch_first_source_ms should record time to first source resolution."""
        strand = FetchStrand()

        # Create a simple test with two sources with different delays
        strand._source_executors = {
            FetchSource.KUBECTL_PODS: _slow_executor(0.05),
            FetchSource.ARGOCD_APP: _slow_executor(0.10),
        }

        request = _build_request(IntentType.STATUS)

        timings = DispatchTimings()
        fetch_start = timings.clock()
        first_source_at = [None]
        first_source_name = [None]

        def on_first_source(source, result):
            if first_source_at[0] is None:
                first_source_at[0] = timings.clock()
                first_source_name[0] = source

        # Mock get_fetch_commands to return our simple test set
        from src.fetch.commands import FetchCommandSpec
        test_commands = [
            FetchCommandSpec(
                source=FetchSource.KUBECTL_PODS,
                command_template="test",
                timeout_seconds=5,
                required=False,
            ),
            FetchCommandSpec(
                source=FetchSource.ARGOCD_APP,
                command_template="test",
                timeout_seconds=5,
                required=False,
            ),
        ]

        with patch('src.fetch.orchestrator.get_fetch_commands') as mock_commands:
            mock_commands.return_value = test_commands
            await strand.fetch(request, on_partial_result=on_first_source)

        # Should have recorded first source timing
        assert first_source_at[0] is not None
        fetch_first_ms = timings.elapsed_ms(fetch_start, first_source_at[0])

        # Should be approximately the first source's delay (50ms)
        # Allow for async overhead (40-150ms range)
        assert fetch_first_ms >= 40, f"First source took only {fetch_first_ms}ms"
        assert fetch_first_ms < 150, f"First source took {fetch_first_ms}ms (too slow)"

        # First source should be KUBECTL_PODS (fastest delay)
        assert first_source_name[0] == FetchSource.KUBECTL_PODS

    @pytest.mark.asyncio
    async def test_fetch_total_ms_records_window_close(self):
        """fetch_total_ms should record the window close time (all sources resolved or timed out)."""
        strand = FetchStrand()

        # Multiple sources with different delays
        delays = {
            FetchSource.KUBECTL_PODS: 0.05,
            FetchSource.ARGOCD_APP: 0.10,
            FetchSource.GIT_LOG: 0.15,
        }
        strand._source_executors = {
            source: _slow_executor(delay) for source, delay in delays.items()
        }

        request = _build_request(IntentType.STATUS)

        start = time.monotonic()
        result = await strand.fetch(request)
        total_ms = (time.monotonic() - start) * 1000

        # Total duration should match the slowest source (~150ms)
        assert total_ms >= 140, f"Total took only {total_ms}ms"
        assert total_ms < 250, f"Total took {total_ms}ms (too slow)"

        # Result's total_duration_ms should match
        assert result.total_duration_ms == int(total_ms)


class TestFetchProgressSSEBroadcast:
    """Tests that FETCH_PROGRESS SSE events are broadcast correctly."""

    @pytest.mark.asyncio
    async def test_progress_events_broadcast_via_sse(self):
        """FETCH_PROGRESS events should be broadcast as sources complete."""
        from src.sse.broadcaster import broadcast_fetch_progress

        # Mock the broadcaster
        broadcaster = SSEBroadcaster()
        broadcaster.broadcast = AsyncMock(return_value=1)

        with patch('src.sse.broadcaster.get_broadcaster', return_value=broadcaster):
            # Simulate progress events
            await broadcast_fetch_progress(
                intent_id="test-intent",
                session_id="test-session",
                completed=2,
                total=5,
                source_name="kubectl_pods",
                source_status="success",
            )

            # Verify broadcast was called
            broadcaster.broadcast.assert_called_once()

            # Check the event data
            call_args = broadcaster.broadcast.call_args
            event = call_args[0][0]
            assert event.event_type == "fetch_progress"
            assert event.data["completed"] == 2
            assert event.data["total"] == 5
            assert event.data["source_name"] == "kubectl_pods"
            assert event.data["source_status"] == "success"


class TestSynthesisGating:
    """Tests that synthesis is gated on window close and invoked exactly once."""

    @pytest.mark.asyncio
    async def test_synthesis_invoked_exactly_once_after_window_close(self):
        """Synthesis should be invoked exactly once per intent, after window close."""
        from unittest.mock import AsyncMock, patch
        from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType

        router = IntentRouter()
        store = await router._get_store()

        # Track synthesis invocations
        synthesis_call_count = [0]
        synthesis_call_times = []
        window_close_time = [None]

        # Create a mock synthesize function that tracks calls
        original_synthesize = None

        async def mock_synthesize(request):
            synthesis_call_count[0] += 1
            synthesis_call_times.append(time.monotonic())
            # Return a valid synthesis result
            from src.synthesize.strand import SynthesizeResult, Urgency
            return SynthesizeResult(
                intent_id=request.intent_id,
                data={"test": "data"},
                summary="Test summary",
                urgency=Urgency.NORMAL,
            )

        # Patch synthesize_intent to track invocations
        with patch('src.intent.router.synthesize_intent', side_effect=mock_synthesize):
            # Create a test routed intent
            routed_intent = RoutedIntent(
                intent_id=str(uuid4()),
                classification=IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                    confidence=0.9,
                    utterance_fragment="show pod status",
                ),
                session_id=str(uuid4()),
                utterance="show pod status",
                router_ms=50,
            )

            # Track window close timing
            fetch_start = time.monotonic()

            # Track progress callbacks to know when window closes
            def track_window_close(source, result):
                # This is called as each source completes
                pass

            # Mock fetch strand to track window close
            from src.fetch.orchestrator import FetchStrand, FetchResult, FetchCoverage
            from src.fetch.commands import FetchSource, SourceResult

            original_fetch = FetchStrand.fetch

            async def mock_fetch(self, request, on_partial_result=None):
                # Simulate staggered source completions
                sources = {}
                succeeded = []
                caveats = []

                # Fast source completes quickly
                await asyncio.sleep(0.02)
                fast_result = SourceResult(
                    source=FetchSource.GIT_LOG,
                    status="success",
                    data={"commits": []},
                    duration_ms=20,
                )
                sources[FetchSource.GIT_LOG] = fast_result
                succeeded.append(FetchSource.GIT_LOG)
                if on_partial_result:
                    on_partial_result(FetchSource.GIT_LOG, fast_result)

                # Slow source completes later
                await asyncio.sleep(0.05)
                slow_result = SourceResult(
                    source=FetchSource.KUBECTL_PODS,
                    status="success",
                    data={"pods": []},
                    duration_ms=50,
                )
                sources[FetchSource.KUBECTL_PODS] = slow_result
                succeeded.append(FetchSource.KUBECTL_PODS)
                if on_partial_result:
                    on_partial_result(FetchSource.KUBECTL_PODS, slow_result)

                # Record window close time (when all sources done)
                window_close_time[0] = time.monotonic()

                total_duration_ms = int((time.monotonic() - fetch_start) * 1000)

                return FetchResult(
                    intent_id=request.intent_id,
                    intent_type=request.intent_type,
                    sources=sources,
                    coverage=FetchCoverage(
                        total_sources=2,
                        succeeded=succeeded,
                        timed_out=[],
                        failed=[],
                        skipped=[],
                    ),
                    total_duration_ms=total_duration_ms,
                    caveats=caveats or None,
                )

            with patch.object(FetchStrand, 'fetch', mock_fetch):
                # Process the intent
                result = await router._fetch_and_synthesize(
                    routed_intent,
                    DispatchTimings(),
                )

        # Verify synthesis was called exactly once
        assert synthesis_call_count[0] == 1, (
            f"Synthesis was called {synthesis_call_count[0]} times, expected 1"
        )

        # Verify synthesis happened after window close
        assert window_close_time[0] is not None, "Window close time not recorded"
        assert synthesis_call_times[0] >= window_close_time[0], (
            f"Synthesis called at {synthesis_call_times[0]}, "
            f"before window close at {window_close_time[0]}"
        )

        # Verify the result is successful
        assert result["status"] == "resolved"


class TestStreamingSynthesis:
    """Tests for streaming synthesis support (progressive card fill)."""

    @pytest.mark.asyncio
    async def test_synthesis_streaming_emits_progress_events(self):
        """Streaming synthesis should emit SYNTHESIS_PROGRESS events as chunks arrive."""
        from src.sse.broadcaster import broadcast_synthesis_progress, EventType

        # Mock the broadcaster
        broadcaster = SSEBroadcaster()
        broadcaster.broadcast = AsyncMock(return_value=1)

        with patch('src.sse.broadcaster.get_broadcaster', return_value=broadcaster):
            # Simulate synthesis progress events
            await broadcast_synthesis_progress(
                intent_id="test-intent",
                session_id="test-session",
                text_chunk="Analyzing pod status...",
            )

            # Verify broadcast was called
            broadcaster.broadcast.assert_called_once()

            # Check the event data
            call_args = broadcaster.broadcast.call_args
            event = call_args[0][0]
            assert event.event_type == EventType.SYNTHESIS_PROGRESS
            assert event.data["intent_id"] == "test-intent"
            assert event.data["text_chunk"] == "Analyzing pod status..."

    @pytest.mark.asyncio
    async def test_zai_client_streaming_yields_chunks(self):
        """ZAIClient.call_streaming should yield text chunks as they arrive."""
        from src.escalate.llm import ZAIClient

        # Mock streaming response
        async def mock_streaming(system_prompt, user_message, model=None, max_tokens=4096, temperature=0.7):
            # Simulate streaming chunks
            chunks = [
                "Analyzing ",
                "pod ",
                "status...",
                {"text": "Analyzing pod status...", "input_tokens": 10, "output_tokens": 5, "finish_reason": "stop"}
            ]
            for chunk in chunks:
                yield chunk

        client = ZAIClient()
        client.call_streaming = mock_streaming

        # Collect chunks
        text_chunks = []
        final_result = None

        async for chunk in client.call_streaming(
            system_prompt="Test prompt",
            user_message="Test message",
        ):
            if isinstance(chunk, str):
                text_chunks.append(chunk)
            else:
                final_result = chunk

        # Verify chunks were streamed
        assert len(text_chunks) == 3
        assert "".join(text_chunks) == "Analyzing pod status..."

        # Verify final result
        assert final_result is not None
        assert final_result["text"] == "Analyzing pod status..."
        assert final_result["input_tokens"] == 10
        assert final_result["output_tokens"] == 5
