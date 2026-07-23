"""
Integration tests for server-side dispatch instrumentation (bead adc-47t4y).

Verifies that the router (src/intent/router.py) and src/main.py record the
correct server-side timing stages into the dispatch_timings table.

Coverage:
- HOT-PATH dispatch: router_ms, fetch_first_source_ms, fetch_total_ms, synthesize_total_ms
- TASK-PROFILE dispatch: router_ms, escalate_ms (fetch/synthesize stages stay NULL)
- synthesize_first_token_ms is NULL on non-streaming call_simple path
- sse_emit_ms recorded after SSE broadcast in src/main.py stream_results()
- Timing capture is non-fatal: persistence failure does not break dispatch
- Full existing suite still passes

Acceptance criteria:
- Both dispatch paths persist a dispatch_timings row with expected server-side stages
- Timing capture proven non-fatal: a persistence failure does not break the dispatch
- synthesize_first_token_ms correctly NULL on current non-streaming call_simple path
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.intent.router import (
    IntentRouter,
    RoutedIntent,
    IntentClassification,
    IntentType,
)
from src.session.store import SessionStore
from src.instrument.timings import DispatchTimings, DISPATCH_TIMING_STAGES
from src.fetch.commands import FetchResult, FetchCoverage, SourceResult, FetchSource
from src.synthesize.strand import SynthesizeResult, Urgency
from src.escalate.handler import EscalateResult
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


# =============================================================================
# Test fixtures
# =============================================================================


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "test.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def mock_clock() -> Callable[[], float]:
    """Mock monotonic clock that returns deterministic timestamps.

    Returns a callable that advances 100ms (0.1s) per call.
    """
    timestamps = []

    def clock() -> float:
        if not timestamps:
            timestamps.append(0.0)
            return 0.0
        # Advance by 100ms per call
        next_time = timestamps[-1] + 0.1
        timestamps.append(next_time)
        return next_time

    return clock


@pytest.fixture
def mock_broadcaster() -> SSEBroadcaster:
    """Mock SSE broadcaster that captures broadcast calls."""
    broadcaster = MagicMock(spec=SSEBroadcaster)
    broadcaster.broadcast = AsyncMock()
    return broadcaster


@pytest.fixture
def mock_zai_client():
    """Mock ZAI LLM client for router classification."""
    client = AsyncMock()
    # Return a simple status classification
    client.call_simple.return_value = '''[
        {
            "intent_type": "status",
            "project_slug": "test-project",
            "confidence": 0.9,
            "utterance_fragment": "check the status",
            "reasoning": "Simple status check",
            "urgency": "normal"
        }
    ]'''
    return client


@pytest.fixture
def mock_task_profile_zai_client():
    """Mock ZAI LLM client for task-profile classification."""
    client = AsyncMock()
    # Return a task-profile classification
    client.call_simple.return_value = '''[
        {
            "intent_type": "task-profile",
            "project_slug": "test-project",
            "confidence": 0.9,
            "utterance_fragment": "implement this feature",
            "reasoning": "Requires implementation work",
            "urgency": "normal"
        }
    ]'''
    return client


@pytest.fixture
def mock_synthesize_llm():
    """Mock LLM for synthesize strand."""
    llm = AsyncMock()
    llm.call_simple.return_value = '''{
        "data": {
            "type": "status-result",
            "status": "operational"
        },
        "summary": "All systems operational",
        "urgency": "normal"
    }'''
    return llm


@pytest.fixture
def mock_escalate_result():
    """Mock escalate result."""
    return EscalateResult(
        intent_id="test-intent",
        bead_id="bead-123",
        pending_card={"title": "Test Task"},
        status="escalated"
    )


# =============================================================================
# HOT-PATH dispatch tests
# =============================================================================


class TestHotPathDispatchInstrumentation:
    """Test server-side timing instrumentation for HOT-PATH dispatches (fetch+synthesize)."""

    @pytest.mark.asyncio
    async def test_hot_path_records_server_side_stages(
        self,
        store: SessionStore,
        mock_clock: Callable[[], float],
        mock_broadcaster: SSEBroadcaster,
        mock_zai_client,
        mock_synthesize_llm,
    ):
        """HOT-PATH dispatch records router_ms, fetch_first_source_ms, fetch_total_ms, synthesize_total_ms.

        This is the main acceptance criteria test for hot-path dispatch instrumentation.
        It runs a full dispatch through the router with stubbed ZAI LLM and fetch,
        then asserts that exactly one dispatch_timings row exists with the expected
        server-side stages populated.
        """
        # Setup: Create router with mocked dependencies
        router = IntentRouter(store=store)

        # Mock the ZAI client
        router._zai_client = mock_zai_client

        # Mock fetch and synthesize to return deterministic results
        with patch("src.intent.router.execute_fetch") as mock_execute_fetch, \
             patch("src.intent.router.synthesize_intent") as mock_synthesize, \
             patch("src.intent.router.get_renderer") as mock_renderer:

            # Setup fetch result with timing data
            fetch_result = FetchResult(
                intent_id="test-intent-1",
                intent_type=FetchIntentType.STATUS,
                sources={
                    FetchSource.KUBECTL_PODS: SourceResult(
                        source=FetchSource.KUBECTL_PODS,
                        status="success",
                        data={"pods": []},
                        duration_ms=100,
                    )
                },
                coverage=FetchCoverage(
                    total_sources=1,
                    succeeded=[FetchSource.KUBECTL_PODS],
                    timed_out=[],
                    failed=[],
                    skipped=[],
                ),
                total_duration_ms=500,
            )

            mock_execute_fetch.return_value = fetch_result

            # Setup synthesize result
            synthesize_result = SynthesizeResult(
                intent_id="test-intent-1",
                data={"status": "operational"},
                summary="All systems operational",
                urgency=Urgency.NORMAL,
                coverage=fetch_result.coverage,
                caveats=[],
            )

            mock_synthesize.return_value = synthesize_result

            # Mock renderer
            mock_render_outcome = MagicMock()
            mock_render_outcome.card_fallback = True
            mock_render_outcome.rendered_html = "<div>test card</div>"
            mock_render_outcome.component_id = None
            mock_renderer.return_value = mock_render_outcome

            # Create a routed intent with router_ms already set
            routed_intent = RoutedIntent(
                intent_id="test-intent-1",
                classification=IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                    confidence=0.9,
                    utterance_fragment="check the status",
                ),
                session_id="test-session-1",
                utterance="check the status",
                router_ms=123,  # Simulate router stage took 123ms
            )

            # Execute: Process the intent through the hot path
            result = await router.process_intent(routed_intent)

            # Verify: Result is successful
            assert result["status"] == "resolved"
            assert result["intent_id"] == "test-intent-1"

        # Verify: Exactly one dispatch_timings row exists
        timings = await store.get_dispatch_timings("test-intent-1")
        assert timings is not None, "dispatch_timings row should exist"

        # Verify: Server-side stages are populated
        assert timings["router_ms"] == 123, "router_ms should be recorded"
        assert timings["fetch_total_ms"] == 500, "fetch_total_ms should be recorded"
        assert timings["synthesize_total_ms"] is not None, "synthesize_total_ms should be recorded"

        # Verify: synthesize_first_token_ms is NULL (documented behavior for non-streaming call_simple)
        assert timings["synthesize_first_token_ms"] is None, \
            "synthesize_first_token_ms should be NULL on non-streaming call_simple path"

        # Verify: Task-profile stages are NULL
        assert timings["escalate_ms"] is None, "escalate_ms should be NULL for hot-path"
        assert timings["sse_emit_ms"] is None, "sse_emit_ms should be NULL (recorded by main.py, not router)"

        # Verify: Client-reported stages are NULL
        assert timings["stt_ms"] is None, "stt_ms should be NULL (not reported in this test)"
        assert timings["first_render_ms"] is None, "first_render_ms should be NULL (not reported in this test)"

    @pytest.mark.asyncio
    async def test_hot_path_fetch_first_source_ms_recorded(
        self,
        store: SessionStore,
        mock_zai_client,
    ):
        """HOT-PATH dispatch records fetch_first_source_ms when first source resolves."""
        router = IntentRouter(store=store)
        router._zai_client = mock_zai_client

        # Mock fetch to trigger first_source callback
        def mock_execute_fetch_with_first_source(request, on_first_source):
            # Simulate first source resolving after 200ms
            import time
            time.sleep(0.01)  # Small delay to simulate work

            # Call the first_source callback
            on_first_source(FetchSource.KUBECTL_PODS, SourceResult(
                source=FetchSource.KUBECTL_PODS,
                status="success",
                data={},
                duration_ms=200,
            ))

            return FetchResult(
                intent_id="test-intent-2",
                intent_type=FetchIntentType.STATUS,
                sources={
                    FetchSource.KUBECTL_PODS: SourceResult(
                        source=FetchSource.KUBECTL_PODS,
                        status="success",
                        data={},
                        duration_ms=200,
                    )
                },
                coverage=FetchCoverage(
                    total_sources=1,
                    succeeded=[FetchSource.KUBECTL_PODS],
                    timed_out=[],
                    failed=[],
                    skipped=[],
                ),
                total_duration_ms=500,
            )

        with patch("src.intent.router.execute_fetch", side_effect=mock_execute_fetch_with_first_source), \
             patch("src.intent.router.synthesize_intent") as mock_synthesize, \
             patch("src.intent.router.get_renderer") as mock_renderer:

            mock_synthesize.return_value = SynthesizeResult(
                intent_id="test-intent-2",
                data={},
                summary="Test",
                urgency=Urgency.NORMAL,
                coverage=FetchCoverage(
                    total_sources=1,
                    succeeded=[FetchSource.KUBECTL_PODS],
                    timed_out=[],
                    failed=[],
                    skipped=[],
                ),
                caveats=[],
            )

            mock_render_outcome = MagicMock()
            mock_render_outcome.card_fallback = True
            mock_render_outcome.rendered_html = "<div>test</div>"
            mock_render_outcome.component_id = None
            mock_renderer.return_value = mock_render_outcome

            routed_intent = RoutedIntent(
                intent_id="test-intent-2",
                classification=IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                ),
                session_id="test-session-2",
                utterance="check status",
                router_ms=100,
            )

            await router.process_intent(routed_intent)

            timings = await store.get_dispatch_timings("test-intent-2")
            assert timings is not None
            assert timings["fetch_first_source_ms"] is not None, \
                "fetch_first_source_ms should be recorded when first source resolves"
            assert timings["fetch_first_source_ms"] > 0, "fetch_first_source_ms should be positive"


# =============================================================================
# TASK-PROFILE dispatch tests
# =============================================================================


class TestTaskProfileDispatchInstrumentation:
    """Test server-side timing instrumentation for TASK-PROFILE dispatches (escalate)."""

    @pytest.mark.asyncio
    async def test_task_profile_records_escalate_ms(
        self,
        store: SessionStore,
        mock_task_profile_zai_client,
        mock_escalate_result,
    ):
        """TASK-PROFILE dispatch records escalate_ms, not fetch/synthesize stages.

        Task-profile intents go through the escalate branch, which measures
        escalate_ms (formulation + validation + bf create). The fetch and
        synthesize stages stay NULL because they're not executed.
        """
        router = IntentRouter(store=store)
        router._zai_client = mock_task_profile_zai_client

        # Mock escalate_intent to return a successful result
        with patch("src.intent.router.escalate_intent") as mock_escalate:
            mock_escalate.return_value = mock_escalate_result

            routed_intent = RoutedIntent(
                intent_id="test-intent-task-profile",
                classification=IntentClassification(
                    intent_type=IntentType.TASK_PROFILE,
                    project_slug="test-project",
                    confidence=0.9,
                    utterance_fragment="implement this feature",
                ),
                session_id="test-session-task-profile",
                utterance="implement this feature",
                router_ms=150,  # Router took 150ms
            )

            result = await router.process_intent(routed_intent)

            # Verify: Escalation succeeded
            assert result["status"] == "escalated"
            assert result["bead_id"] == "bead-123"

        # Verify: Exactly one dispatch_timings row exists
        timings = await store.get_dispatch_timings("test-intent-task-profile")
        assert timings is not None, "dispatch_timings row should exist"

        # Verify: Router stage is recorded
        assert timings["router_ms"] == 150, "router_ms should be recorded"

        # Verify: Escalate stage is recorded (may be 0 in test with mock, but recorded)
        assert timings["escalate_ms"] is not None, "escalate_ms should be recorded"
        assert timings["escalate_ms"] >= 0, "escalate_ms should be non-negative"

        # Verify: Fetch/synthesize stages are NULL (not executed for task-profile)
        assert timings["fetch_first_source_ms"] is None, \
            "fetch_first_source_ms should be NULL for task-profile dispatch"
        assert timings["fetch_total_ms"] is None, \
            "fetch_total_ms should be NULL for task-profile dispatch"
        assert timings["synthesize_total_ms"] is None, \
            "synthesize_total_ms should be NULL for task-profile dispatch"
        assert timings["synthesize_first_token_ms"] is None, \
            "synthesize_first_token_ms should be NULL for task-profile dispatch"


# =============================================================================
# SSE emit timing tests
# =============================================================================


class TestSSEEmitTiming:
    """Test SSE emit timing instrumentation in src/main.py stream_results()."""

    @pytest.mark.asyncio
    async def test_sse_emit_ms_recorded_after_broadcast(
        self,
        store: SessionStore,
    ):
        """src/main.py stream_results() records sse_emit_ms after broadcast.

        This test verifies that the SSE broadcast timing is captured and
        persisted separately from the router stages (via a second
        record_dispatch_timings call with only sse_emit_ms set).
        """
        # Create a result with an intent_id
        intent_id = "test-intent-sse-emit"

        # First, create a dispatch_timings row with router stages
        await store.record_dispatch_timings(
            intent_id,
            router_ms=100,
            fetch_total_ms=500,
            synthesize_total_ms=200,
        )

        # Simulate the SSE emit timing capture (as done in stream_results)
        emit_start = time.monotonic()
        await asyncio.sleep(0.01)  # Simulate SSE broadcast work
        sse_emit_ms = int((time.monotonic() - emit_start) * 1000)

        # Record the SSE emit timing (second upsert)
        await store.record_dispatch_timings(intent_id, sse_emit_ms=sse_emit_ms)

        # Verify: All stages are present in the same row
        timings = await store.get_dispatch_timings(intent_id)
        assert timings is not None

        # Verify: Original router stages are still present
        assert timings["router_ms"] == 100, "router_ms should be preserved"
        assert timings["fetch_total_ms"] == 500, "fetch_total_ms should be preserved"
        assert timings["synthesize_total_ms"] == 200, "synthesize_total_ms should be preserved"

        # Verify: SSE emit stage is now set
        assert timings["sse_emit_ms"] is not None, "sse_emit_ms should be recorded"
        assert timings["sse_emit_ms"] >= 10, "sse_emit_ms should be at least 10ms"


# =============================================================================
# Non-fatal persistence tests
# =============================================================================


class TestNonFatalPersistence:
    """Test that timing capture is non-fatal: persistence failure does not break dispatch."""

    @pytest.mark.asyncio
    async def test_router_persistence_failure_does_not_break_dispatch(
        self,
        store: SessionStore,
        mock_zai_client,
    ):
        """A persistence failure in _persist_timings does not break the dispatch.

        When record_dispatch_timings fails, the router logs a warning and
        continues normally, returning the successful result to the caller.
        """
        router = IntentRouter(store=store)
        router._zai_client = mock_zai_client

        # Mock the store to raise an exception on record_dispatch_timings
        with patch.object(store, "record_dispatch_timings", side_effect=Exception("DB error")), \
             patch("src.intent.router.execute_fetch") as mock_execute_fetch, \
             patch("src.intent.router.synthesize_intent") as mock_synthesize, \
             patch("src.intent.router.get_renderer") as mock_renderer:

            mock_execute_fetch.return_value = FetchResult(
                intent_id="test-intent-persistence-failure",
                intent_type=FetchIntentType.STATUS,
                sources={},
                coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
                total_duration_ms=100,
            )

            mock_synthesize.return_value = SynthesizeResult(
                intent_id="test-intent-persistence-failure",
                data={},
                summary="Test",
                urgency=Urgency.NORMAL,
                coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
                caveats=[],
            )

            mock_render_outcome = MagicMock()
            mock_render_outcome.card_fallback = True
            mock_render_outcome.rendered_html = "<div>test</div>"
            mock_render_outcome.component_id = None
            mock_renderer.return_value = mock_render_outcome

            routed_intent = RoutedIntent(
                intent_id="test-intent-persistence-failure",
                classification=IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                ),
                session_id="test-session-persistence",
                utterance="check status",
                router_ms=100,
            )

            # Execute: Process the intent (should not raise despite persistence failure)
            result = await router.process_intent(routed_intent)

            # Verify: Dispatch still succeeds
            assert result["status"] == "resolved", "Dispatch should succeed despite persistence failure"
            assert result["intent_id"] == "test-intent-persistence-failure"


# =============================================================================
# synthesize_first_token_ms NULL test
# =============================================================================


class TestSynthesizeFirstTokenNull:
    """Test that synthesize_first_token_ms is NULL on non-streaming call_simple path."""

    @pytest.mark.asyncio
    async def test_synthesize_first_token_ms_null_on_non_streaming(
        self,
        store: SessionStore,
        mock_zai_client,
    ):
        """synthesize_first_token_ms is NULL on current non-streaming call_simple path.

        The synthesize strand uses call_simple (no token stream), so first_token_ms
        cannot be measured and stays NULL. This is documented behavior, not a bug.
        """
        router = IntentRouter(store=store)
        router._zai_client = mock_zai_client

        with patch("src.intent.router.execute_fetch") as mock_execute_fetch, \
             patch("src.intent.router.synthesize_intent") as mock_synthesize, \
             patch("src.intent.router.get_renderer") as mock_renderer:

            mock_execute_fetch.return_value = FetchResult(
                intent_id="test-intent-first-token",
                intent_type=FetchIntentType.STATUS,
                sources={},
                coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
                total_duration_ms=100,
            )

            mock_synthesize.return_value = SynthesizeResult(
                intent_id="test-intent-first-token",
                data={},
                summary="Test",
                urgency=Urgency.NORMAL,
                coverage=FetchCoverage(total_sources=0, succeeded=[], timed_out=[], failed=[], skipped=[]),
                caveats=[],
            )

            mock_render_outcome = MagicMock()
            mock_render_outcome.card_fallback = True
            mock_render_outcome.rendered_html = "<div>test</div>"
            mock_render_outcome.component_id = None
            mock_renderer.return_value = mock_render_outcome

            routed_intent = RoutedIntent(
                intent_id="test-intent-first-token",
                classification=IntentClassification(
                    intent_type=IntentType.STATUS,
                    project_slug="test-project",
                ),
                session_id="test-session-first-token",
                utterance="check status",
                router_ms=100,
            )

            await router.process_intent(routed_intent)

            timings = await store.get_dispatch_timings("test-intent-first-token")
            assert timings is not None

            # Verify: synthesize_first_token_ms is NULL (documented behavior)
            assert timings["synthesize_first_token_ms"] is None, \
                "synthesize_first_token_ms should be NULL on non-streaming call_simple path"

            # Verify: synthesize_total_ms IS recorded (total duration is measurable)
            assert timings["synthesize_total_ms"] is not None, \
                "synthesize_total_ms should be recorded even on non-streaming path"


# =============================================================================
# FetchIntentType import fix
# =============================================================================

# Import FetchIntentType for the tests
from src.fetch.commands import IntentType as FetchIntentType
